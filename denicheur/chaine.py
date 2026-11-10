"""CHAÎNE EAN (10/11/2026) : la vérification unique des deux dénicheurs.

Règle : la lecture des pages ne sert plus qu'à DÉCOUVRIR des candidats. Une proposition d'achat n'existe que si
  1. le produit est rattaché à un code EAN (ou un ASIN Amazon, converti en EAN par Keepa) LU dans les données de la
     fiche du marchand — jamais deviné d'après le nom ;
  2. le prix d'achat est confirmé dans les données de cette fiche (ou par Keepa pour Amazon) ;
  3. le marché français est interrogé PAR CE CODE : Keepa (Amazon : prix, ventes, vendeurs) + Google Shopping
     (les autres marchands, port compris) ;
  4. le verdict applique les seuils de David (écart, concurrence, marge nette).
Tout candidat qui échoue à une étape est jeté, et la raison est comptée (data/chaine.json, « entonnoir »).

Deux entrées, une seule vérification :
  - Idéfix (bleu)  : promo -> demande. Candidats = bons plans du jour (Dealabs, chaînes Telegram, LDLC…).
  - Amigo  (jaune) : demande -> promo. Candidats = produits qui se vendent vraiment (ventes Amazon 30 jours, Keepa),
    pour lesquels on cherche le marchand le moins cher.
Bingo = feu vert, quel que soit le dénicheur. Étoile = le même EAN sort vert/orange des deux côtés.
"""
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.parse

from . import keepa, lecteur, meme_produit, shopping
from .rentabilite import calculer
from .verif_prix import _Page, _num, _types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIX_MIN, PRIX_MAX = 20, 600
ECART_MIN = 15          # % sous le moins cher des autres marchands
ECART_ANORMAL = 70      # au-delà : presque toujours une erreur de lecture ou un autre produit -> jamais vert
MARGE_VERTE, MARGE_ENVOI = 20, 10
CANAL = "rebifftout"    # vente sur son site, livraison directe du marchand au client (un seul port)
SOUS_LE_MARCHE = 0.97   # on revend 3 % sous le moins cher des autres marchands

FR = re.compile(r"\.fr\b|amazon|cdiscount|fnac|darty|boulanger|leroy ?merlin|castorama|brico ?d[ée]p[ôo]t|bricoman|"
                r"electro ?d[ée]p[ôo]t|rue ?du ?commerce|ldlc|materiel\.net|carrefour|leclerc|auchan|conforama|\bbut\b|"
                r"decathlon|micromania|cultura|lidl|la redoute|gifi|weldom|mr ?bricolage|ubaldi|son-?vid[ée]o|top ?achat|"
                r"grosbill|cybertek|manomano|rakuten|pccomponentes\.fr|alternate\.fr|king ?jouet|jou[ée]club|intersport", re.I)
EXCLUS = re.compile(r"leboncoin|ebay|vinted|stockx|back ?market|beebs|achatmoinscher|idealo|ledenicheur|occasion|"
                    r"reconditionn|refurb|rebuy|easy ?cash|cash ?converters|aliexpress|temu|joom|wish\b|fruugo|onbuy", re.I)
GROS = re.compile(r"amazon|fnac|darty|boulanger|cdiscount|carrefour|leclerc|auchan|leroy ?merlin|\bbut\b|conforama|ldlc|"
                  r"rue ?du ?commerce|manomano|decathlon|castorama|electro ?d[ée]p[ôo]t|rakuten", re.I)
ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})(?:[/?#]|$)")
PAYS_AMAZON = {"amazon.fr": "FR", "amazon.de": "DE", "amazon.it": "IT", "amazon.es": "ES"}


# ------------------------------------------------------------------ codes
def ean_valide(code):
    """Vrai seulement pour un GTIN-8/12/13/14 dont la clé de contrôle est juste (un code inventé ou tronqué est refusé)."""
    c = re.sub(r"\D", "", str(code or ""))
    if len(c) not in (8, 12, 13, 14) or len(set(c)) == 1:
        return False
    corps, cle = c[:-1], int(c[-1])
    somme = sum(int(ch) * (3 if i % 2 == 0 else 1) for i, ch in enumerate(reversed(corps)))
    return (10 - somme % 10) % 10 == cle


def ean13(code):
    c = re.sub(r"\D", "", str(code or ""))
    return c.lstrip("0").zfill(13) if ean_valide(c) else None


def domaine(url):
    h = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def asin_de(url):
    d = domaine(url)
    if "amazon." not in d:
        return None, None
    m = ASIN.search(urllib.parse.urlsplit(url).path + "/")
    # amazon.com : le robot tourne aux États-Unis et Amazon y renvoie parfois les liens courts français ; le code produit
    # est le même, et Keepa confirme ensuite que la fiche existe bien sur Amazon France.
    pays = next((p for k, p in PAYS_AMAZON.items() if d.endswith(k)), "FR" if d.endswith("amazon.com") else None)
    return (m.group(1) if m else None), pays


# ------------------------------------------------------------------ fiche du marchand (données intégrées)
def produits_page(h):
    """Tous les objets Product du JSON-LD de la page (premier niveau et @graph, pas les recommandations imbriquées)."""
    page = _Page()
    page.feed(h or "")
    out = []
    for s in page.scripts:
        try:
            d = json.loads(s)
        except (ValueError, TypeError):
            continue
        for o in (d if isinstance(d, list) else [d]):
            if not isinstance(o, dict):
                continue
            for n in ([o] + [g for g in (o.get("@graph") or []) if isinstance(g, dict)]):
                if _types(n) & {"Product", "ProductGroup"}:
                    out.append(n)
                    out.extend(v for v in (n.get("hasVariant") or []) if isinstance(v, dict))
    return out


def _codes(p):
    vals = [p.get(k) for k in ("gtin13", "gtin", "gtin14", "gtin12", "gtin8", "ean", "isbn")]
    return {ean13(v) for v in vals if ean13(v)}


def _offres(p):
    o = p.get("offers") or []
    o = o if isinstance(o, list) else [o]
    plates = []
    for x in o:
        if isinstance(x, dict):
            plates.extend([y for y in (x.get("offers") or []) if isinstance(y, dict)] if "AggregateOffer" in _types(x) and x.get("offers") else [x])
    return plates


def lire_fiche(h, ean_attendu=None):
    """Renvoie {ean, prix, etat, dispo, titre, marque} lus dans les DONNÉES de la page, ou {'raison': …}.
    Refuse toute page ambiguë : plusieurs produits/variantes avec des codes différents, plusieurs prix en stock."""
    prods = [p for p in produits_page(h) if _codes(p) or _offres(p)]
    if not prods:
        return {"raison": "aucune donnée produit dans la page"}
    avec_code = [p for p in prods if _codes(p)]
    if ean_attendu:
        avec_code = [p for p in avec_code if ean_attendu in _codes(p)]
        if not avec_code:
            return {"raison": "le code attendu n'est pas dans la page"}
    codes = set().union(*[_codes(p) for p in avec_code]) if avec_code else set()
    if not codes:
        return {"raison": "pas de code EAN dans la page"}
    if len(codes) > 1:
        return {"raison": f"page à variantes ({len(codes)} codes EAN différents)"}
    p = avec_code[0]
    prix, etats, dispo = [], set(), False
    for o in _offres(p):
        if str(o.get("priceCurrency", "EUR")).upper() != "EUR":
            continue
        en_stock = str(o.get("availability", "")).rstrip("/").split("/")[-1].lower() in ("instock", "onlineonly", "limitedavailability", "")
        n = _num(o.get("price") if o.get("price") is not None else o.get("lowPrice"))
        if n is not None and en_stock:
            prix.append(n)
            dispo = True
            etats.add(str(o.get("itemCondition", "")).rstrip("/").split("/")[-1].lower() or "newcondition")
    marque = p.get("brand")
    marque = marque.get("name") if isinstance(marque, dict) else marque
    res = {"ean": next(iter(codes)), "titre": str(p.get("name") or "")[:160], "marque": marque if isinstance(marque, str) else None,
           "dispo": dispo, "etat": "neuf" if etats <= {"newcondition"} else "pas neuf"}
    if not prix:
        return {**res, "prix": None, "raison": "prix ou stock absent des données"}
    if max(prix) - min(prix) > 0.011:
        return {**res, "prix": None, "raison": "plusieurs prix dans les données de la page"}
    return {**res, "prix": prix[0]}


# ------------------------------------------------------------------ Keepa par lots
def keepa_lot(valeurs, par="asin", pays="FR", attente_max=600):
    """Fiches Keepa pour ≤ 100 ASIN ou codes EAN en UNE requête (1 jeton par produit). {asin|ean13: fiche}.
    Attend la recharge des jetons (20/minute) au lieu d'échouer."""
    valeurs = [v for v in dict.fromkeys(valeurs) if v][:100]
    if not valeurs or not keepa.cle():
        return {}
    params = {"key": keepa.cle(), "domain": keepa.DOMAINES.get(pays, 4), "stats": 90, "history": 0,
              ("asin" if par == "asin" else "code"): ",".join(valeurs)}
    debut, d = time.monotonic(), None
    while True:
        try:
            d = keepa._lire(params)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or time.monotonic() - debut > attente_max:
                return {}
            time.sleep(60)   # jetons épuisés : 20 de plus par minute
        except Exception:
            return {}
    b = keepa._budget()
    keepa._noter(b, d.get("tokensLeft"))
    out = {}
    for p in d.get("products") or []:
        if not isinstance(p, dict) or not p.get("asin"):
            continue
        f = keepa._parser(p, params["domain"], pays, d.get("tokensLeft"))
        f["eans"] = sorted({ean13(c) for c in (p.get("eanList") or []) + (p.get("upcList") or []) if ean13(c)})
        f["ventes_mois"] = p.get("monthlySold") if isinstance(p.get("monthlySold"), int) else None
        if par == "asin":
            out[p["asin"]] = f
        else:
            for c in f["eans"]:
                if c in valeurs:
                    out.setdefault(c, []).append(f)
    if par != "asin":   # un code qui renvoie plusieurs produits Amazon : on garde le plus vendu, en le signalant
        for c, fs in list(out.items()):
            fs.sort(key=lambda f: -(f.get("chutes_rang_30j") or 0))
            out[c] = {**fs[0], "nb_fiches_amazon": len(fs)}
    return out


# ------------------------------------------------------------------ marché français par EAN
VIDES = {"avec", "sans", "pour", "the", "and", "noir", "noire", "blanc", "blanche", "black", "white", "lot", "pack", "fil",
         "homme", "femme", "new", "neuf", "pro", "max", "plus", "mini", "les", "des", "eur"}


def _mots(t):
    return set(re.findall(r"[a-z0-9]{3,}", meme_produit._n(t or ""))) - VIDES


ACCESSOIRE = re.compile(r"\b(housse|coque|etui|kit|cable|piece|pieces|remplacement|compatible|coussinets?|support|protection|"
                        r"minifigs?|eclairage|accessoire|chargeur|batterie de rechange|filtre|sac|brossettes?|cartouches?|"
                        r"telecommande|verre trempe|film|adaptateur|camera supplementaire)\b")


def _refs(t):
    """Références de modèle : mots contenant un chiffre (a30s, t50, 42214, 16gb)."""
    mots = re.findall(r"[a-z0-9]{2,}", meme_produit._n(t or ""))
    # « 850w », « 13000pa », « 60min », « 16go » sont des caractéristiques, pas des références de modèle
    carac = re.compile(r"\d+(w|l|cl|ml|go|gb|tb|to|mah|pa|kpa|mm|cm|m|min|h|kg|g|db|mhz|hz|v|pcs|k|x|eur|en|in)?")
    return {x for x in mots if re.search(r"\d", x) and not (carac.fullmatch(x) and not re.fullmatch(r"\d{4,6}", x))}


def concorde(ref, titre, marque=None):
    """La fiche Google est-elle le même produit que la fiche du marchand ? Simple TRI, jamais une preuve (la preuve est
    le code EAN chez idealo). Il faut : pas de contradiction mécanique, la MARQUE dans les deux titres, aucun mot
    d'accessoire en plus (housse, kit, câble…), et les références de modèle de la fiche Google toutes présentes dans
    le titre du marchand. Deux titres sans aucune référence : tous les mots de la fiche Google doivent être dans le titre du marchand."""
    if not ref or not titre or meme_produit.mecanique(ref, titre)[0] is False:
        return False
    na, nb = meme_produit._n(ref), meme_produit._n(titre)
    if ACCESSOIRE.search(nb) and not ACCESSOIRE.search(na):
        return False
    a, b = _mots(ref), _mots(titre)
    m = _mots(marque) or set(list(re.findall(r"[a-z0-9]{3,}", na))[:1])
    if not m or not (m & b):
        return False
    ra, rb = _refs(ref), _refs(titre)
    if rb:
        return bool(ra) and rb <= ra
    if ra:
        return False   # le marchand cite un modèle précis, Google non : impossible de dire que c'est le même
    reste_b = b - m
    return len(reste_b) >= 2 and reste_b <= a   # tous les mots de la fiche Google sont dans le titre du marchand


def requete_google(titre, marque=None):
    """Recherche Google Shopping par NOM court (marque + début du titre). Constat du 10/11 sur 99 codes : interrogé par
    code EAN, Google Shopping renvoie des produits sans aucun rapport (figurines, vinyles, câbles) ; le code ne sert donc
    qu'à relier la fiche du marchand à Amazon (Keepa), et c'est `concorde` (marque + référence du modèle) qui garantit
    que la fiche Google est bien le même produit."""
    t = re.sub(r"[\[\(].*?[\]\)]", " ", titre or "")
    t = re.split(r",| - | – | \| ", t)[0]
    mots = [m for m in re.sub(r"[^\w\s.+/-]", " ", t).split() if m][:7]
    if marque and marque.lower() not in " ".join(mots).lower():
        mots.insert(0, marque)
    return " ".join(mots)[:80]


def marche_google(eans, titres, marques=None):
    """{ean: {'fiche': titre Google, 'vendeurs': [{marchand, total, gros, lien}]}} — recherche par nom court, fiche
    retenue seulement si elle concorde (marque + modèle), puis vendeurs de cette fiche."""
    marques = marques or {}
    req = {e: requete_google(titres.get(e), marques.get(e)) for e in eans}
    par_req = shopping.chercher([q for q in req.values() if q], "FR", attente_max=240)
    res = {e: par_req.get(req[e], []) for e in eans}
    choix = {}
    for e in eans:
        ref = titres.get(e) or ""
        for o in res.get(e, []):
            if not o.get("product_id") or not o.get("titre"):
                continue
            if not concorde(ref, o["titre"], (marques or {}).get(e)):
                continue
            choix[e] = o
            break
    vend = shopping.vendeurs([o["product_id"] for o in choix.values()], "FR", attente_max=240) if choix else {}
    out = {}
    for e in eans:
        o = choix.get(e)
        if not o:
            out[e] = {"fiche": None, "vendeurs": [], "raison": "produit introuvable sur Google Shopping" if not res.get(e) else "fiche Google non concordante",
                      "refusees": [x.get("titre") for x in res.get(e, [])[:4]]}
            continue
        vs, vus = [], set()
        for v in vend.get(o["product_id"], []):
            nom = str(v.get("marchand") or "")
            ident = f"{nom} {v.get('lien') or ''}"
            if v.get("etat") not in (None, "", "new", "neuf") or not FR.search(ident) or EXCLUS.search(ident):
                continue
            total = v.get("total") or round(v["prix"] + (v.get("port") or 0), 2)
            cle = re.sub(r"[^a-z0-9]", "", nom.lower())[:14]
            if cle in vus:
                continue
            vus.add(cle)
            vs.append({"marchand": nom, "total": round(float(total), 2), "gros": bool(GROS.search(ident)), "lien": v.get("lien")})
        vs.sort(key=lambda v: v["total"])
        out[e] = {"fiche": o["titre"], "vendeurs": vs}
    return out


# ------------------------------------------------------------------ idealo par code (la preuve)
def idealo_par_code(ean, nom=None):
    """Prix neuf le plus bas de France pour CE code EAN, lu chez idealo (robot Apify, ≈ 0,01 $ par recherche).
    On cherche par le code, puis par le nom ; dans les deux cas une fiche n'est acceptée que si son code EAN est
    exactement celui du produit. Renvoie {prix_min, nb_offres, lien, titre} ou {'raison': …}."""
    from . import apify
    apify.CONTEXTE["denicheur"] = "A"
    vu = False
    for q in (ean, nom):
        if not q:
            continue
        items = apify.lancer("idealo", {"searchQuery": q, "country": "FR", "maxItems": 3, "fetchOffers": False}, maxi=3)
        if items is None:
            return {"raison": "idealo indisponible (plafond du jour ou robot en panne)"}
        vu = vu or bool(items)
        for i in items:
            if isinstance(i, dict) and ean13(i.get("gtin")) == ean and isinstance(i.get("price"), (int, float)) and i["price"] > 0:
                return {"prix_min": float(i["price"]), "nb_offres": i.get("offerCount"), "lien": i.get("url"), "titre": i.get("title")}
    return {"raison": "idealo a des fiches proches mais aucune avec ce code" if vu else "produit absent d'idealo"}


# ------------------------------------------------------------------ verdict
def verdict(achat, refs, prix_confirme=True, regles=None, ventes_30j=None, preuve_code=False):
    """achat : prix d'achat confirmé. refs : [{marchand, total, gros}] = les AUTRES marchands français, neuf, port compris.
    Seuils de David : ≥ 10 vendeurs dont un gros site à notre prix = on passe ; 5-9 = seulement si ≥ 15 % moins cher ;
    ≤ 4 et moins cher = bon. Vert = marge nette ≥ 20 €, prix confirmé, deux marchands d'accord sur le prix de référence."""
    regles = regles or json.load(open(os.path.join(RACINE, "config/regles.json"), encoding="utf-8"))
    refs = sorted([r for r in refs if isinstance(r.get("total"), (int, float)) and r["total"] > 0], key=lambda r: r["total"])
    v = {"achat": achat, "nb_vendeurs": len(refs), "ventes_30j": ventes_30j, "manque": [], "feu": "rouge"}
    if not achat:
        v["raison"] = "prix d'achat non confirmé"
        return v
    if not refs:
        v["raison"] = "aucun autre marchand français trouvé pour ce code"
        return v
    ref = refs[0]
    v.update({"ref_min": ref["total"], "ref_ou": ref["marchand"], "ref_lien": ref.get("lien"),
              "ref_mediane": round(statistics.median(r["total"] for r in refs), 2),
              "ecart_pct": round((1 - achat / ref["total"]) * 100, 1)})
    v["prix_vente"] = round(ref["total"] * SOUS_LE_MARCHE, 2)
    detail = calculer(v["prix_vente"], CANAL, achat, regles)
    v["marge_nette"], v["calcul_marge"] = detail["marge_nette"], detail
    proches = [r for r in refs if r["total"] <= achat * 1.05]
    v["gros_au_meme_prix"] = [r["marchand"] for r in proches if r.get("gros")]
    seuil = ECART_MIN if len(refs) >= 5 else 5
    if v["ecart_pct"] < seuil:
        v["raison"] = f"pas moins cher que le marché ({v['ecart_pct']} % sous {ref['marchand']})"
    elif len(refs) >= 10 and v["gros_au_meme_prix"]:
        v["raison"] = f"concurrence trop forte ({len(refs)} vendeurs, {v['gros_au_meme_prix'][0]} au même prix)"
    elif v["marge_nette"] < MARGE_ENVOI:
        v["raison"] = f"marge nette trop faible ({v['marge_nette']} €)"
    else:
        if v["marge_nette"] < MARGE_VERTE:
            v["manque"].append(f"marge nette sous {MARGE_VERTE} €")
        if v["ecart_pct"] < ECART_MIN:
            v["manque"].append(f"seulement {v['ecart_pct']} % sous le marché")
        if not prix_confirme:
            v["manque"].append("prix d'achat à confirmer sur la fiche")
        if preuve_code:
            pass   # la référence est le prix le plus bas de France pour CE code (idealo) : pas besoin d'un second avis
        elif len(refs) < 2:
            v["manque"].append("un seul marchand de référence")
        elif refs[1]["total"] > ref["total"] * 1.25:
            v["manque"].append("les deux marchands de référence ne sont pas d'accord (écart > 25 %)")
        if v["ecart_pct"] >= ECART_ANORMAL:
            v["manque"].append(f"écart anormal ({v['ecart_pct']} %) : à vérifier à la main")
        v["feu"] = "orange" if v["manque"] else "vert"
    return v


# ------------------------------------------------------------------ identification d'un candidat (Idéfix, ou lien collé)
def lien_marchand(lien):
    """Du lien de l'annonce au lien du marchand. Les sites Pepper (Dealabs…) passent par /visit/threadmain/<id>."""
    d = domaine(lien)
    if any(d.endswith(p) for p in lecteur.PEPPER):
        m = re.search(r"-(\d{5,9})(?:[/?#]|$)", lien)
        if not m:
            return None
        time.sleep(1.5)
        return lecteur._redirection(f"https://www.{d}/visit/threadmain/{m.group(1)}", referer=lien)
    if d in ("amzn.to", "amzn.eu", "a.co", "bit.ly", "tidd.ly", "s.click.aliexpress.com") or "/visit/" in lien:
        return lecteur._redirection(lien) or lien
    return lien


def identifier(c):
    """Complète le candidat : lien_marchand, domaine, puis soit asin (Amazon) soit ean + prix_page (autres marchands).
    Renvoie le candidat ; c['rejet'] est rempli quand il ne peut pas être identifié."""
    url = lien_marchand(c.get("lien") or "")
    if not url:
        c["rejet"] = "lien du marchand introuvable"
        return c
    c["lien_marchand"], c["domaine"] = url, domaine(url)
    asin, pays = asin_de(url)
    if "amazon." in c["domaine"]:
        if not asin or pays != "FR":
            c["rejet"] = "Amazon hors France" if asin else "lien Amazon sans fiche produit (liste, boutique, recherche)"
            return c
        c["asin"] = asin
        return c
    code, fin, h = lecteur._get(url)
    if code != 200 or lecteur.MOTS_BLOCAGE.search((h or "")[:3000]):
        c["rejet"] = f"fiche du marchand illisible depuis le cloud ({code})"
        return c
    f = lire_fiche(h)
    c["fiche_page"] = f
    if not f.get("ean"):
        c["rejet"] = f.get("raison")
        return c
    if f.get("etat") != "neuf":
        c["rejet"] = "produit pas neuf"
        return c
    c["ean"], c["prix_page"], c["titre_fiche"] = f["ean"], f.get("prix"), f.get("titre")
    if f.get("prix") is None:
        c["rejet"] = f.get("raison")
    return c
