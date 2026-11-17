"""MARCHÉ D'UNE AFFAIRE « écart vendeurs » (demande de David, 17/11/2026).

Pour chaque produit trouvé avec un gros écart, avant l'alerte Telegram :
 1. le produit se vend-il DÉJÀ sur Leboncoin, Vinted et eBay ? Nombre d'annonces, prix de la moins chère à la plus chère ;
 2. à quel prix le moins cher on le trouve dans les COMPARATEURS de prix (idealo, achatmoinscher) ;
 3. le VOLUME de recherche Google (voir `volumes`).

Coûts : eBay et achatmoinscher gratuits. Vinted, Leboncoin et idealo passent par les robots Apify déjà payés
(0,05 $ réservés par affaire, ≈ 0,03 $ au réel), sous un plafond à part « E » de 0,40 $ par jour (denicheur/apify.py) :
la veille garde tout son plafond « A ». Les recherches partent en parallèle (une affaire est étudiée en ≈ 1 minute).
Une source qui ne répond pas est notée « non consultée » : jamais un chiffre inventé, jamais « aucune annonce » à tort.
"""
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import comparateurs

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOTS_VIDES = {"de", "du", "des", "la", "le", "les", "un", "une", "et", "ou", "à", "a", "au", "aux", "avec", "pour", "sans",
              "en", "sur", "par", "the", "and", "with", "for", "of", "pack", "lot", "set", "kit", "neuf", "nouveau", "new"}
PLANCHER, PLAFOND = 0.30, 2.0   # une annonce sous 30 % de notre achat = accessoire ; au-dessus de 2 fois le 2e vendeur = lot
PLAFOND_ROBOT = 0.015           # $ au plus par recherche Vinted (15 annonces) ; Leboncoin 0,02 $ ; idealo 0,015 $


def nom_court(titre, marque=None, n=4):
    """Nom tel qu'un particulier l'écrit : marque + premiers mots utiles du titre (n au plus), sans mots vides."""
    t = re.sub(r"[\[\(].*?[\]\)]", " ", titre or "")
    t = re.split(r",| - | – | \| ", t)[0]
    mots = [m for m in re.sub(r"[^\w\s.+/-]", " ", t).split() if m.lower() not in MOTS_VIDES]
    if marque and marque.lower() not in " ".join(mots).lower():
        mots.insert(0, marque)
    return " ".join(mots[:n]).lower()


def variantes(nom):
    """Du nom précis au nom plus large (3 mots au moins) : sert au volume de recherche, sans coût en plus (même appel)."""
    m = nom.split()
    return [nom] + ([" ".join(m[:3])] if len(m) >= 4 else [])


def _sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn")


def meme(titre, nom):
    """Même produit, d'après le titre d'une annonce de particulier : mots entiers, sans tenir compte des accents (« néo »)."""
    return comparateurs.correspond(_sans_accents(titre), _sans_accents(nom))


ANCIENNE_J = 21   # une annonce en ligne depuis plus de 3 semaines sans se vendre (remarque de David, 17/11/2026)


def age_jours(date):
    """Nombre de jours depuis la publication (date ISO, ou secondes/millisecondes depuis 1970). None si illisible."""
    from datetime import datetime, timezone
    try:
        if isinstance(date, (int, float)) and date > 0:
            d = datetime.fromtimestamp(date / 1000 if date > 1e11 else date, timezone.utc)
        else:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(date or ""))
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
    except (AttributeError, ValueError, OverflowError, OSError):
        return None
    j = (datetime.now(timezone.utc) - d).days
    return j if 0 <= j < 3650 else None


def _fourchette(annonces):
    """annonces : [(prix, lien, date de publication)] -> {nb, min, max, lien_min} + l'ancienneté des annonces quand la date
    est connue : age_min (jours en ligne de la moins chère), age_recent / age_ancien (la plus récente, la plus ancienne),
    recentes (publiées depuis 7 jours), anciennes (en ligne depuis plus de ANCIENNE_J jours). {nb: 0} si aucune."""
    annonces = sorted(((a[0], a[1], age_jours(a[2]) if len(a) > 2 else None) for a in annonces if a[0]), key=lambda a: a[0])
    if not annonces:
        return {"nb": 0}
    r = {"nb": len(annonces), "min": round(annonces[0][0], 2), "max": round(annonces[-1][0], 2), "lien_min": annonces[0][1]}
    ages = [a[2] for a in annonces if a[2] is not None]
    if ages:
        r.update({"dates": len(ages), "age_min": annonces[0][2], "age_recent": min(ages), "age_ancien": max(ages),
                  "recentes": sum(1 for x in ages if x <= 7), "anciennes": sum(1 for x in ages if x > ANCIENNE_J)})
    return r


def _dans_bornes(p, bas, haut):
    return isinstance(p, (int, float)) and bas <= p <= haut


DATES_VINTED = ("created_at", "created_at_ts", "createdAt", "published_at", "upload_date", "last_push_up_at", "updated_at")


def vinted(nom, bas, haut):
    from . import apify
    items = apify._lancer("vinted", apify.ROBOTS["vinted"][0], PLAFOND_ROBOT,
                          {"mode": "Search Items", "query": nom, "market": "fr", "max_results": 15}, 15)
    if items is None:
        return None
    tout, neufs = [], []
    for i in items:
        if not isinstance(i, dict) or not meme(i.get("title") or "", nom):
            continue
        p = apify._num(i.get("price_amount"))
        if not _dans_bornes(p, bas, haut):
            continue
        date = next((i[k] for k in DATES_VINTED if i.get(k)), None)
        tout.append((p, i.get("url"), date))
        if "neuf" in (i.get("status") or "").lower():
            neufs.append((p, i.get("url"), date))
    return {**_fourchette(tout), "neuf": _fourchette(neufs)}


def leboncoin(nom, bas, haut):
    from . import apify
    annonces = apify.annonces_leboncoin(nom, plafond=0.02)
    if annonces is None:
        return None
    return _fourchette([(p, lien, date) for t, p, lien, date in annonces if meme(t, nom) and _dans_bornes(p, bas, haut)])


def _ebay_appel(tok, params, neuf):
    from . import ebay
    filtres = ["buyingOptions:{FIXED_PRICE}", "priceCurrency:EUR",
               "conditionIds:{1000}" if neuf else "conditionIds:{1500|2000|2500|3000|4000|5000}"]
    q = urllib.parse.urlencode({**params, "limit": 100, "filter": ",".join(filtres)})
    req = urllib.request.Request(f"{ebay.SEARCH_URL}?{q}", headers={
        "Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_FR", "Accept-Language": "fr-FR"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("itemSummaries") or []


def ebay_fr(nom, ean, bas, haut):
    """Annonces en cours sur eBay France (API officielle, gratuite), neuf et occasion séparés (comparaison à état égal)."""
    from . import ebay
    tok = ebay.jeton()
    res = {}
    for cle, neuf in (("neuf", True), ("occasion", False)):
        vus, annonces = set(), []
        lots = [(_ebay_appel(tok, {"q": nom}, neuf), False)]
        if ean:
            try:
                lots.append((_ebay_appel(tok, {"gtin": ean}, neuf), True))  # code-barres : même produit, sans filtre de titre
            except Exception:
                pass
        for items, sur in lots:
            for it in items:
                ident = it.get("itemId")
                if ident in vus or not (sur or meme(it.get("title") or "", nom)):
                    continue
                try:
                    p = float(it["price"]["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                if _dans_bornes(p, bas, haut):
                    vus.add(ident)
                    annonces.append((p, it.get("itemWebUrl"), it.get("itemCreationDate")))
        res[cle] = _fourchette(annonces)
    res["nb"] = res["neuf"]["nb"] + res["occasion"]["nb"]
    return res


def idealo(nom, ean):
    from . import apify
    if not apify.disponible():
        return None
    r = apify.prix_idealo(nom, ean)
    return {"prix_min": r["prix_min"], "nb_offres": r.get("nb_offres"), "lien": r.get("lien")} if r else {"prix_min": None}


def achatmoinscher(nom):
    r = comparateurs.prix_plancher(nom)
    s = (r.get("sources") or {}).get("achatmoinscher") or {}
    if s.get("erreur"):
        return None
    m = s.get("meilleur")
    return {"prix_min": m["prix"], "nb_offres": m.get("nb_boutiques"), "lien": m.get("lien")} if m else {"prix_min": None}


def etudier(affaires):
    """Complète chaque affaire (fiche de denicheur/ecart.py) avec f['marche']. Recherches en parallèle, plafond Apify « E »."""
    from . import apify, sante
    avant = apify.CONTEXTE["denicheur"]
    apify.CONTEXTE["denicheur"] = "E"
    taches = []
    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            for f in affaires:
                nom = f.get("nom_court") or nom_court(f["titre"], f.get("marque"))
                f["nom_court"] = nom
                bas, haut = PLANCHER * f["premier"], PLAFOND * f["second"]
                ean = f.get("ean")
                for cle, fonction, args in (("leboncoin", leboncoin, (nom, bas, haut)), ("vinted", vinted, (nom, bas, haut)),
                                            ("ebay", ebay_fr, (nom, ean, bas, haut)), ("idealo", idealo, (nom, ean)),
                                            ("achatmoinscher", achatmoinscher, (nom,))):
                    taches.append((f, cle, pool.submit(sante.protege, "marché " + cle, fonction, *args, defaut=None)))
            for f, cle, t in taches:
                f.setdefault("marche", {})[cle] = t.result()
    finally:
        apify.CONTEXTE["denicheur"] = avant
    for f in affaires:
        m = f["marche"]
        comp = [(m[c]["prix_min"], c, m[c].get("nb_offres"), m[c].get("lien")) for c in ("idealo", "achatmoinscher")
                if m.get(c) and m[c].get("prix_min")]
        m["comparateurs_consultes"] = [c for c in ("idealo", "achatmoinscher") if m.get(c) is not None]
        if comp:
            p, ou, nb, lien = min(comp, key=lambda c: c[0])
            m["comparateur_min"] = {"prix": p, "ou": ou, "nb_offres": nb, "lien": lien, "ecart": round(p - f["premier"], 2)}
    return affaires


# ---------- volume de recherche ----------
F_SUIVI = os.path.join(RACINE, "data/etat/ecart_volume.json")
def _reserve_du_jour():
    """Réserve du jour pour le volume des écarts, AU-DESSUS du plafond DataForSEO (les passages de nuit le consomment).
    0 tant que David n'a pas donné son accord (config/regles.json : ecart_volume_reserve_usd_jour)."""
    from datetime import datetime, timezone
    from .ecart import _lire
    total = float(_lire(os.path.join(RACINE, "config/regles.json"), {}).get("ecart_volume_reserve_usd_jour", 0) or 0)
    s = _lire(F_SUIVI, {})
    pris = s.get("pris_usd", 0) if s.get("jour") == datetime.now(timezone.utc).strftime("%Y-%m-%d") else 0
    return max(0.0, round(total - pris, 4)), pris


def volumes(noms):
    """{nom: {'v': volume mensuel Google France, 'mot': mot-clé mesuré}} pour chaque nom dont le volume est connu.
    D'abord le cache (gratuit) ; sinon UN appel groupé DataForSEO Labs (≈ 0,013 $) pour tous les noms manquants."""
    from datetime import datetime, timezone
    from . import dataforseo, fiche
    from .ecart import _ecrire
    vol = fiche._cache()
    manquants = sorted({v for n in noms for v in variantes(n) if v not in vol})
    if manquants:
        reste, pris = _reserve_du_jour()
        plafond = dataforseo.plafond_du_jour()   # sans la réserve
        avant = dataforseo._budget()["depense_usd"]
        try:
            with dataforseo.reserve(reste):
                res = dataforseo.volumes_labs(manquants)
        except Exception:
            res = None
        apres = dataforseo._budget()["depense_usd"]
        jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hors_plafond = round(max(0.0, apres - max(avant, plafond)), 4)   # ce que CET appel a pris au-dessus du plafond
        if hors_plafond > 0:
            _ecrire(F_SUIVI, {"jour": jour, "pris_usd": round(pris + hors_plafond, 4)})
        if res is not None:
            for m in manquants:   # appel réussi : un mot absent de la réponse = trop peu recherché pour être mesuré
                vol[m] = {"v": res.get(m) or 0, "d": jour}
            _ecrire(fiche.F_VOL, {k: v for k, v in vol.items() if v.get("d") != "bingo"})
    out = {}
    for n in noms:
        connus = [(v, (vol.get(v) or {}).get("v")) for v in variantes(n) if isinstance((vol.get(v) or {}).get("v"), int)]
        if connus:
            mot, v = next(((m, x) for m, x in connus if x > 0), connus[0])   # le nom précis d'abord, le plus large sinon
            out[n] = {"v": v, "mot": mot}
    return out


# ---------- texte Telegram ----------
def _eur(v):
    return f"{v:.2f}".replace(".", ",").replace(",00", "") + " €" if isinstance(v, (int, float)) else "—"


def _lien(texte, url):
    from html import escape
    return f'<a href="{escape(url, quote=True)}">{texte}</a>' if url else texte


def _depuis(j):
    return "aujourd'hui" if j == 0 else f"depuis {j} j"


def _ligne(nom, r, etat=""):
    if r is None:
        return f" • {nom} : non consulté"
    if not r.get("nb"):
        return f" • {nom} : aucune annonce{etat}"
    n = r["nb"]
    prix = f"de {_eur(r['min'])} à {_eur(r['max'])}" if n > 1 and r["max"] > r["min"] else f"à {_eur(r['min'])}"
    t = f" • {nom} : {n} annonce{'s' if n > 1 else ''}{etat}, {prix} ({_lien('la moins chère', r.get('lien_min'))}"
    t += (f", en ligne {_depuis(r['age_min'])}" if r.get("age_min") is not None else "") + ")"
    if r.get("dates") and n > 1:   # ancienneté des annonces : ce qui traîne ne se vend pas
        t += f"\n     📅 {r['recentes']} publiée{'s' if r['recentes'] > 1 else ''} cette semaine · {r['anciennes']} en ligne depuis plus de {ANCIENNE_J} j"
        t += f" · la plus ancienne : {r['age_ancien']} j"
    return t


def lignes(f):
    """Lignes à insérer dans l'alerte : comparateurs, puis présence sur Leboncoin / Vinted / eBay."""
    m = f.get("marche")
    if not m:
        return []
    t = []
    c = m.get("comparateur_min")
    noms = {"idealo": "idealo", "achatmoinscher": "achatmoinscher"}
    if c:
        offres = f", {c['nb_offres']} offres" if c.get("nb_offres") else ""
        ligne = f"🧭 Comparateurs de prix : le moins cher à <b>{_eur(c['prix'])}</b> ({_lien(noms[c['ou']], c.get('lien'))}{offres})"
        if c["ecart"] >= 5:
            ligne += f" → ton achat est <b>{_eur(c['ecart'])} en dessous</b> ✅"
        elif c["ecart"] > -5:
            ligne += " → ⚠️ déjà affiché à ce prix dans les comparateurs"
        elif c["prix"] < 0.7 * f["premier"]:   # trouvé par le nom, très en dessous : le plus souvent un autre modèle (Bodum 1,5 L, 17/11)
            ligne += " → ❓ bien moins cher que ton achat : sans doute un autre modèle, à vérifier sur le lien"
        else:
            ligne += f" → ⚠️ {_eur(-c['ecart'])} MOINS CHER que ton achat"
        t.append(ligne)
    elif m.get("comparateurs_consultes"):
        t.append(f"🧭 Comparateurs de prix : introuvable sur {' et '.join(m['comparateurs_consultes'])} ✅ (personne ne le voit à ce prix)")
    else:
        t.append("🧭 Comparateurs de prix : non consultés")
    t.append("♻️ Déjà en vente ailleurs ?")
    t.append(_ligne("Leboncoin", m.get("leboncoin")))
    v = m.get("vinted")
    t.append(_ligne("Vinted", v) + (f" — dont {v['neuf']['nb']} en neuf dès {_eur(v['neuf']['min'])}" if v and v.get("nb") and v["neuf"].get("nb") else ""))
    e = m.get("ebay")
    if e is None:
        t.append(_ligne("eBay", None))
    elif not e.get("nb"):
        t.append(" • eBay : aucune annonce")
    else:
        t.append(_ligne("eBay neuf", e["neuf"]))
        t.append(_ligne("eBay occasion", e["occasion"]))
    # une annonce déjà moins chère que le prix de revente conseillé, sur les sites de revente visés
    revente = (f.get("marges") or {}).get("prix_revente")
    bas = [(r["min"], s) for s, r in (("Leboncoin", m.get("leboncoin")), ("Vinted", (v or {}).get("neuf") if v else None),
                                      ("eBay", (e or {}).get("neuf") if e else None)) if r and r.get("nb")]
    if revente and bas and min(bas)[0] < revente:
        p, s = min(bas)
        t.append(f"⚠️ Déjà à {_eur(p)} sur {s} : sous le prix de revente conseillé ({_eur(revente)})")
    # la moins chère traîne depuis plus de 3 semaines : personne n'en veut à ce prix, ou l'annonce est mal faite
    vieux = [(r["min"], s, r["age_min"]) for s, r in (("Leboncoin", m.get("leboncoin")), ("Vinted", v), ("eBay neuf", (e or {}).get("neuf") if e else None),
                                                       ("eBay occasion", (e or {}).get("occasion") if e else None))
             if r and r.get("nb") and (r.get("age_min") or 0) > ANCIENNE_J]
    for p, s, j in vieux:
        t.append(f"⏳ {s} : l'annonce à {_eur(p)} est en ligne depuis {j} j sans se vendre (peu de demande, ou annonce mal faite)")
    return t
