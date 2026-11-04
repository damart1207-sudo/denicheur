"""HYPE ÉTRANGÈRE DU JOUR sur Telegram (demande de David, 04/11) : ce qui cartonne aux USA / au Japon et n'a pas
encore explosé en France, avec les mêmes informations que les annonces pour décider d'ANTICIPER.
Source : data/hype_etranger.json (meilleures ventes Amazon US/JP comparées à Amazon.fr, moisson Keepa).
Par produit : rang là-bas, prix là-bas, situation en France (absent / mal vendu, prix FR), recherches Google France
et leur évolution sur 3 mois, coût d'import estimé, prix de revente visé, bénéfice estimé, verdict.
Coût : Gemini (mots-clés, quelques centimes, cache) + DataForSEO 1 appel (≈ 0,09 $), une fois par jour (passage de nuit)."""
import json
import os
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_SORTIE = os.path.join(RACINE, "data/hype_telegram.json")
F_VOL = os.path.join(RACINE, "data/base/volumes_hype.json")
F_VOL_ORIG = os.path.join(RACINE, "data/base/volumes_origine.json")
TAUX = {"US": 0.90, "JP": 0.0058}       # devise -> euros (prudent)
PORT = {"US": 15, "JP": 12}             # envoi vers la France, estimation
IMPORT = 1.25                           # TVA 20 % + droits ≈ 5 %
FRAIS_VENTE = 0.12                      # commission plateforme + emballage


def _lire(f, d):
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return d


def prix_eur(x):
    p = x.get("prix_labas")
    if not isinstance(p, (int, float)):
        return None
    if x.get("pays") == "JP":
        p = p * 100  # Keepa Japon : prix en yens stockés divisés par 100 par la moisson
    return round(p * TAUX.get(x.get("pays"), 1), 2)


def candidats(jours=7, n=50):
    limite = (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%d")
    vus, out = set(), []
    for x in sorted(_lire(os.path.join(RACINE, "data/hype_etranger.json"), {}).get("produits", []),
                    key=lambda x: (x.get("vu", "") < limite, x.get("rang_labas") or 999)):
        pe = prix_eur(x)
        if x["asin"] in vus or (x.get("vu") or "") < limite or not pe or pe < 20:
            continue
        vus.add(x["asin"])
        out.append({**x, "prix_eur": pe})
        if len(out) >= n:
            break
    return out


EXCLUS = ("gift card", "digital code", "carte cadeau", "us version", "subscription", "membership", "diaper", "wipes", "refill")
DEJA_CONNU = 5000   # au-delà, le produit est déjà connu en France (sous une autre référence) : ce n'est plus une hype à venir


def evaluer(x, v):
    """v = {volume_mensuel, trois_derniers_mois} (France) ou None.
    Produit absent d'Amazon.fr : on ne connaît pas encore son prix français -> on donne le PRIX MINIMUM de revente
    pour gagner 20 € (jamais un prix inventé) ; il ne peut pas être vert. Vert seulement si un prix français existe,
    que le bénéfice tient et que les recherches françaises existent."""
    cout = round((x["prix_eur"] + PORT.get(x["pays"], 15)) * IMPORT, 2)
    if x.get("offres"):
        cout = min(cout, x["offres"][0]["cout"])  # la source la moins chère (souvent un Amazon européen : pas de douane)
    prix_mini = round((cout + 20) / (1 - FRAIS_VENTE), 2)
    vol = (v or {}).get("volume_mensuel")
    hist = [h for h in (v or {}).get("trois_derniers_mois") or [] if isinstance(h, (int, float))]
    tendance = round((hist[0] / hist[-1] - 1) * 100) if len(hist) >= 2 and hist[-1] else None
    f = {"cout_import": cout, "prix_mini": prix_mini, "volume_fr": vol, "tendance_fr_pct": tendance, "manque": [],
         "revente": None, "benefice": None, "anticiper": False}
    t = (x.get("titre") or "").lower()
    if any(e in t for e in EXCLUS):
        f["feu"], f["raison"] = "rouge", "produit exclu (numérique, consommable, version US)"
        return f
    if x.get("prix_fr"):
        f["revente"] = round(x["prix_fr"] * 0.95, 2)
        f["benefice"] = round(f["revente"] * (1 - FRAIS_VENTE) - cout, 2)
        if f["benefice"] <= 0:
            f["feu"], f["raison"] = "rouge", "pas de bénéfice"
            return f
    elif vol is not None and vol >= DEJA_CONNU:
        f["feu"], f["raison"] = "rouge", "déjà connu en France sous une autre référence"
        return f
    f["anticiper"] = bool(tendance is not None and tendance >= 20 and (vol or 0) < DEJA_CONNU)
    if vol is None:
        f["manque"].append("recherches France inconnues")
    elif vol < 300 and not f["anticiper"]:
        f["manque"].append(f"presque personne ne le cherche en France ({vol}/mois)")
    if not x.get("prix_fr"):
        f["manque"].append("pas encore vendu en France : prix de revente à tester")
    elif f["benefice"] < 20:
        f["manque"].append("bénéfice sous 20 €")
    f["feu"] = "vert" if not f["manque"] else "orange"
    return f


PORT_UE = 8                                     # achat dans l'UE : port seul, ni douane ni TVA d'import
DOMAINES_PRIX = ("FR", "DE", "IT", "ES", "US", "JP")


def _eur_keepa(p, pays):
    if not isinstance(p, (int, float)) or p <= 0:
        return None
    if pays == "JP":
        return round(p * 100 * TAUX["JP"], 2)
    return round(p * TAUX.get(pays, 1), 2)


def enrichir(cands, mots):
    """Prix le plus bas (Amazon FR/DE/IT/ES/US/JP via Keepa, 1 jeton par produit et par pays ; eBay USA gratuit),
    ventes du mois sur chaque Amazon (« achetés le mois dernier ») et annonces eBay USA, volume de recherche dans le pays d'origine."""
    from . import moisson, ebay, dataforseo
    asins = [c["asin"] for c in cands]
    par_pays = {}
    for pays in DOMAINES_PRIX:
        try:
            par_pays[pays] = {r["asin"]: r for r in moisson.fiches(asins, pays)}
        except Exception:
            par_pays[pays] = {}
    try:
        tok = ebay.jeton()
    except Exception:
        tok = None
    for c in cands:
        offres, ventes = [], {}
        for pays, d in par_pays.items():
            r = d.get(c["asin"])
            if not r:
                continue
            p = _eur_keepa(r.get("neuf"), pays)
            if p:
                ue = pays in ("FR", "DE", "IT", "ES")
                offres.append({"ou": f"Amazon {pays}", "prix": p,
                               "cout": round(p + (0 if pays == "FR" else PORT_UE), 2) if ue else round((p + PORT.get(pays, 15)) * IMPORT, 2)})
            if r.get("vendus_mois") or r.get("ch30"):
                ventes[f"Amazon {pays}"] = r.get("vendus_mois") or f"≈{r.get('ch30')}"
        if tok and c["pays"] == "US":
            try:
                pr, _ = ebay.chercher(tok, c.get("mot_cle") or ebay.requete(c["titre"]), marche="EBAY_US", neuf=True)
                pr = sorted(pr)
                if pr:
                    ventes["eBay USA (annonces)"] = len(pr)
                    p = round(pr[0] * TAUX["US"], 2)
                    offres.append({"ou": "eBay USA", "prix": p, "cout": round((p + PORT["US"]) * IMPORT, 2)})
            except Exception:
                pass
        o = par_pays.get(c["pays"], {}).get(c["asin"]) or {}
        c["croissance_ventes_pct"] = round((o["r90"] / o["r30"] - 1) * 100) if o.get("r30") and o.get("r90") else None
        c["offres"] = sorted(offres, key=lambda o: o["cout"])
        c["vendeurs_fr"] = (par_pays.get("FR", {}).get(c["asin"]) or {}).get("offres")
        c["ventes"] = ventes
    # volume de recherche dans le pays d'origine (un appel par pays, ≈ 0,09 $ chacun)
    cache = _lire(F_VOL_ORIG, {})
    for pays in sorted({c["pays"] for c in cands}):
        a_faire = sorted({c["mot_cle"] for c in cands if c["pays"] == pays and c.get("mot_cle") and f"{pays}:{c['mot_cle']}" not in cache})
        if a_faire and dataforseo.disponible(0.09):
            res = dataforseo.volumes(a_faire, pays=pays)
            if res:
                for m in a_faire:
                    cache[f"{pays}:{m}"] = res.get(m) or {"volume_mensuel": 0}
    os.makedirs(os.path.dirname(F_VOL_ORIG), exist_ok=True)
    json.dump(cache, open(F_VOL_ORIG, "w", encoding="utf-8"), ensure_ascii=False)
    for c in cands:
        c["volume_origine"] = (cache.get(f"{c['pays']}:{c.get('mot_cle')}") or {}).get("volume_mensuel")


CROISSANCE_MIN = 10   # % : le rang de vente moyen des 30 derniers jours meilleur que celui des 90 jours


def approfondir(cands, maxi=20):
    """Règle de David : ventes ET recherches en hausse sur 30 jours (pays d'origine) -> analyse approfondie :
    prix le moins cher (déjà calculé), livrable en France (eBay, filtre livraison France), concurrents en France
    sur toutes nos sources (Amazon.fr, eBay France, annonces collectées, idealo)."""
    from . import dataforseo, ebay
    montent = [c for c in cands if (c.get("croissance_ventes_pct") or 0) >= CROISSANCE_MIN and c.get("mot_cle")][:maxi]
    # recherches Google sur 30 jours dans le pays d'origine (Google Trends, 5 mots par appel, ≈ 0,011 $)
    for pays in sorted({c["pays"] for c in montent}):
        mots = [c["mot_cle"] for c in montent if c["pays"] == pays]
        for i in range(0, len(mots), 5):
            res = dataforseo.tendances(mots[i:i + 5], pays=pays, periode="past_30_days") or {}
            for c in montent:
                t = res.get(c["mot_cle"])
                if c["pays"] == pays and t:
                    c["recherches_30j"] = t["tendance"]
    try:
        tok = ebay.jeton()
    except Exception:
        tok = None
    annonces = []
    for fch in ("data/etat/annonces_recentes.json", "data/pc/annonces.json"):
        d = _lire(os.path.join(RACINE, fch), [])
        annonces += d if isinstance(d, list) else d.get("annonces", [])
    for c in montent:
        if c.get("recherches_30j") != "monte":
            continue
        c["double_hausse"] = True
        a = {}
        q = c["mot_cle"]
        if tok:
            for marche, nom in (("EBAY_US", "eBay USA"), ("EBAY_GB", "eBay UK")):
                try:
                    pr, ex = ebay.chercher(tok, q, marche=marche, neuf=True, livrable_fr=True, limite=50)
                    if pr:
                        a.setdefault("livrable_fr", []).append({"ou": nom, "annonces": len(pr), "prix_min": round(min(pr) * TAUX.get("US", 1) if marche == "EBAY_US" else min(pr) * 1.17, 2),
                                                                "lien": (ex[0] or {}).get("url") if ex else None})
                except Exception:
                    pass
            try:
                pr, _ = ebay.chercher(tok, q, marche="EBAY_FR", neuf=True)
                a["ebay_fr_neuf"] = len(pr)
            except Exception:
                pass
        mots = set(q.lower().split())
        a["annonces_collectees_fr"] = sum(1 for x in annonces if isinstance(x, dict) and mots <= set(str(x.get("titre", "")).lower().split()))
        a["vendeurs_amazon_fr"] = c.get("vendeurs_fr")
        try:
            from . import apify
            if apify.disponible():
                a["idealo"] = apify.prix_idealo(q)
        except Exception:
            pass
        c["analyse"] = a
    return [c for c in cands if c.get("double_hausse")]


def analyse_txt(c, telegram):
    a = c["analyse"]
    liv = a.get("livrable_fr") or []
    t = ("🚚 Livrable en France : " + " · ".join(f"{telegram._e(l['ou'])} {l['annonces']} annonces dès {telegram._eur(l['prix_min'])}" for l in liv)
         if liv else "🚚 Livrable en France : aucune annonce eBay USA/UK trouvée (voir Amazon DE/ES ci-dessous)") + "\n"
    conc = [f"Amazon.fr {a['vendeurs_amazon_fr']} vendeurs" if a.get("vendeurs_amazon_fr") is not None else "absent d'Amazon.fr",
            f"eBay France {a.get('ebay_fr_neuf', '?')} annonces neuves", f"nos sources {a.get('annonces_collectees_fr', 0)} annonces"]
    if a.get("idealo"):
        conc.append(f"idealo {a['idealo'].get('nb_offres') or '?'} offres dès {telegram._eur(a['idealo'].get('prix_min'))}")
    return t + "⚔️ Concurrents en France : " + telegram._e(" · ".join(conc)) + "\n"


def prix_mini_txt(f):
    return f["prix_mini"]


def jour(n_envoi=10, envoyer=True):
    from . import bingo, dataforseo, telegram
    cands = candidats()
    if not cands:
        return 0
    mots = bingo.mots_cles_ia([c["titre"] for c in cands], maxi_appels=3) or {}
    cache = _lire(F_VOL, {})
    for c in cands:
        q = mots.get(c["titre"]) if isinstance(mots, dict) else None
        c["mot_cle"] = q
    manquants = sorted({c["mot_cle"] for c in cands if c.get("mot_cle") and c["mot_cle"] not in cache})
    if manquants and dataforseo.disponible(0.09):
        res = dataforseo.volumes(manquants)
        for m in manquants:
            if res:
                cache[m] = res.get(m) or {"volume_mensuel": 0, "trois_derniers_mois": []}
        os.makedirs(os.path.dirname(F_VOL), exist_ok=True)
        json.dump(cache, open(F_VOL, "w", encoding="utf-8"), ensure_ascii=False)
    enrichir(cands, mots)
    approfondir(cands)
    for c in cands:
        c["fiche"] = evaluer(c, cache.get(c.get("mot_cle")) if c.get("mot_cle") else None)
    rang = {"vert": 0, "orange": 1, "rouge": 2}
    cands.sort(key=lambda c: (not c.get("double_hausse"), rang[c["fiche"]["feu"]], not c["fiche"]["anticiper"], -(c["fiche"]["benefice"] or 0), -(c["fiche"]["volume_fr"] or 0)))
    json.dump({"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "produits": cands},
              open(F_SORTIE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    garder = [c for c in cands if c["fiche"]["feu"] != "rouge"][:n_envoi]
    if not any(c["fiche"]["volume_fr"] is not None for c in cands):
        return 0  # sans les recherches France, le message serait incomplet : on n'envoie rien (règle de David)
    if not envoyer or not garder:
        return len(garder)
    drapeau = {"US": "🇺🇸", "JP": "🇯🇵"}
    lignes = [f"<b>🌍 Hype étrangère du jour</b> — {len(garder)} produits qui cartonnent à l'étranger et pas (encore) en France"]
    for c in garder:
        f = c["fiche"]
        rond = ("🔥 VENTES + RECHERCHES EN HAUSSE · " if c.get("double_hausse") else "") + {"vert": "🟢 VERT", "orange": "🟠 ORANGE"}[f["feu"]]
        tend = ("" if f["tendance_fr_pct"] is None else
                f" ({'📈 +' if f['tendance_fr_pct'] >= 0 else '📉 '}{f['tendance_fr_pct']} % en 3 mois)")
        fr = (f"absent d'Amazon France" if c.get("en_france") == "absent"
              else f"mal vendu en France : {telegram._eur(c.get('prix_fr'))}, rang {c.get('rang_fr')}")
        vol = f["volume_fr"]
        lignes.append(
            f"\n{rond}{' · ⚡ À ANTICIPER' if f['anticiper'] else ''}\n"
            f"<b>{telegram._e((c.get('titre') or '')[:90])}</b>\n"
            f"{drapeau.get(c['pays'], c['pays'])} n° {c.get('rang_labas')} des ventes ({telegram._e(c.get('categorie'))}) · prix là-bas {telegram._eur(c['prix_eur'])}\n"
            f"🇫🇷 {fr}\n"
            f"🔎 Recherches Google France : {('inconnu' if vol is None else str(vol))} /mois{tend}\n"
            + (f"🔎 Recherches Google {telegram._e(c['pays'])} : {c['volume_origine']} /mois\n" if c.get("volume_origine") is not None else "")
            + (f"📈 Ventes là-bas : {'+' if c['croissance_ventes_pct'] >= 0 else ''}{c['croissance_ventes_pct']} % (30 j vs 90 j)"
               + (f" · recherches 30 j : {telegram._e(c['recherches_30j'])}" if c.get("recherches_30j") else "") + "\n"
               if c.get("croissance_ventes_pct") is not None else "")
            + (analyse_txt(c, telegram) if c.get("analyse") else "")
            + (f"🛒 Ventes du mois : {telegram._e(' · '.join(f'{k} {v}' for k, v in c['ventes'].items()))}\n" if c.get("ventes") else "")
            + (f"🏷️ Achat le moins cher rendu chez toi : <b>{telegram._eur(c['offres'][0]['cout'])}</b> sur {telegram._e(c['offres'][0]['ou'])} "
               f"(affiché {telegram._eur(c['offres'][0]['prix'])})"
               + (f" · ensuite {telegram._e(c['offres'][1]['ou'])} {telegram._eur(c['offres'][1]['cout'])}" if len(c['offres']) > 1 else "") + "\n"
               if c.get("offres") else "")
            + (f"🎯 Revente sous le prix Amazon.fr : {telegram._eur(f['revente'])} · 💰 bénéfice estimé <b>{telegram._eur(f['benefice'])}</b>\n"
               if f["revente"] else f"🎯 Pour gagner 20 €, le revendre au moins <b>{telegram._eur(prix_mini_txt(f))}</b>\n")
            + (f"⚠️ {telegram._e(', '.join(f['manque']))}\n" if f["manque"] else "")
            + f"{telegram._e(c.get('lien_fr'))}")
    lignes.append("\n⚡ À ANTICIPER = les recherches françaises montent : le produit arrive. Commander 1 unité test avant d'en prendre plus.")
    paquet = ""
    for bloc in lignes:  # Telegram : 4 096 caractères max par message, on coupe entre deux produits
        if len(paquet) + len(bloc) > 3800:
            telegram.envoyer(paquet)
            paquet = ""
        paquet += bloc + "\n"
    if paquet:
        telegram.envoyer(paquet)
    return len(garder)
