"""MOISSONNEUR Keepa : profite à fond de l'abonnement (20 jetons/minute, réserve plafonnée à 1 200 jetons
qui expirent au bout d'une heure : tout jeton non dépensé dans l'heure est PERDU).

Appelé à chaque tour de veille (toutes les heures) :  python -m denicheur.moisson
Il vide la réserve en trois récoltes, sans jamais descendre sous RESERVE_MIN (pour laisser des jetons
aux fiches du passage de la nuit et de la veille) :

1. RADAR AMAZON (10 jetons) : les baisses de prix Amazon.fr des 24 h (neuf et Seconde main « Warehouse »),
   AVANT qu'elles arrivent sur Dealabs  -> data/radar_amazon.json  (source pour Idéfix).
2. ÉTAGÈRE (≈ 110 jetons par catégorie) : Product Finder par grande catégorie, produits qui se VENDENT
   (chutes de classement sur 30 jours), puis fiche complète de chacun. Les catégories tournent d'un tour à
   l'autre.  -> data/base/keepa/AAAA-MM.jsonl.gz (résumé compact, ≈ 200 octets/produit) + data/base/keepa_index.json
   C'est NOTRE base : à terme, elle remplace Keepa.
3. HYPE ÉTRANGÈRE (≈ 150 jetons par pays) : meilleures ventes Amazon USA / Japon par catégorie, puis les mêmes
   ASIN regardés sur Amazon.fr : ce qui cartonne là-bas et n'est pas (ou mal) vendu en France.
   -> data/hype_etranger.json (source pour Amigo).

Garde-fous : RESERVE_MIN jetons gardés, JETONS_TOUR_MAX par tour, JETONS_JOUR_MAX par jour, aucun achat.
Aucun euro en plus : tout est compris dans l'abonnement. Une erreur n'arrête jamais le tour de veille.
"""
import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import keepa, sante

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_ETAT = os.path.join(RACINE, "data/etat/moisson.json")
F_CATS = os.path.join(RACINE, "data/base/keepa_categories.json")
F_INDEX = os.path.join(RACINE, "data/base/keepa_index.json")
D_BASE = os.path.join(RACINE, "data/base/keepa")
F_RADAR = os.path.join(RACINE, "data/radar_amazon.json")
F_HYPE = os.path.join(RACINE, "data/hype_etranger.json")

RESERVE_MIN = 150            # on ne descend jamais sous ce nombre de jetons (le passage et la veille en ont besoin)
JETONS_TOUR_MAX = 1100       # au plus par tour (la réserve fait 1 200)
JETONS_JOUR_MAX = 24000      # au plus par jour (28 800 possibles)
PRIX_MIN_CENT, PRIX_MAX_CENT = 1200, 45000   # produits entre 12 € et 450 € (ce qu'on sait revendre)
# index des séries Keepa dans stats.current : 0 Amazon, 1 neuf, 2 occasion, 3 rang, 9 Warehouse (Seconde main), 11 nb offres neuves
I_AMAZON, I_NEUF, I_OCCASION, I_RANG, I_WAREHOUSE, I_NB_NEUF = 0, 1, 2, 3, 9, 11
PAYS_HYPE = ("US", "JP")
DOMAINES = {**keepa.DOMAINES, "JP": 5, "SG": 19, "IN": 10}
_jetons = {"restants": None, "depenses": 0}


# ---------- état / fichiers ----------
def _lire(f, defaut):
    try:
        with open(f, encoding="utf-8") as g:
            return json.load(g)
    except (OSError, json.JSONDecodeError):
        return defaut


def _ecrire(f, d, compact=False):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", encoding="utf-8") as g:
        json.dump(d, g, ensure_ascii=False, **({"separators": (",", ":")} if compact else {"indent": 1}))


def _etat():
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    e = _lire(F_ETAT, {})
    if e.get("jour") != jour:
        e = {"jour": jour, "jetons_jour": 0, "tours": 0, "cat_suivante": e.get("cat_suivante", 0),
             "hype_suivante": e.get("hype_suivante", 0), "pays_suivant": e.get("pays_suivant", 0), "produits_jour": 0}
    return e


# ---------- appels Keepa (avec compteur de jetons) ----------
def _appel(chemin, params, corps=None):
    """GET ou POST sur api.keepa.com. Met à jour le compteur de jetons restants (tokensLeft)."""
    attente = 1.1 - (time.time() - keepa._dernier[0])
    if attente > 0:
        time.sleep(attente)
    keepa._dernier[0] = time.time()
    params = {"key": keepa.cle(), **params}
    url = "https://api.keepa.com/" + chemin + "?" + urllib.parse.urlencode(params)
    data = json.dumps(corps).encode() if corps is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "denicheur/1.0", "Accept-Encoding": "gzip",
                                                           **({"Content-Type": "application/json"} if data else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        brut = r.read()
    if brut[:2] == b"\x1f\x8b":
        brut = gzip.decompress(brut)
    d = json.loads(brut)
    if isinstance(d.get("tokensLeft"), int):
        if _jetons["restants"] is not None:
            _jetons["depenses"] += max(0, _jetons["restants"] - d["tokensLeft"])
        _jetons["restants"] = d["tokensLeft"]
    return d


def jetons_restants():
    if _jetons["restants"] is None:
        try:  # 1 jeton : la liste des catégories racine, on en profite pour la garder
            d = _appel("category", {"domain": 4, "category": 0, "parents": 0})
            cats = d.get("categories") or {}
            if cats and not os.path.exists(F_CATS):
                _ecrire(F_CATS, {k: {"nom": v.get("name"), "pays": "FR"} for k, v in cats.items() if isinstance(v, dict)})
        except Exception as e:
            sante.noter("erreur", "moisson jetons", f"{type(e).__name__}: {str(e)[:120]}")
            return 0
    return _jetons["restants"] or 0


def _peut(cout, etat):
    """Assez de jetons pour une récolte qui coûte `cout` ? (réserve, plafond du tour, plafond du jour)"""
    return (jetons_restants() - cout >= RESERVE_MIN and _jetons["depenses"] + cout <= JETONS_TOUR_MAX
            and etat["jetons_jour"] + _jetons["depenses"] + cout <= JETONS_JOUR_MAX)


# ---------- résumé compact d'une fiche produit ----------
def _prix(c):
    return round(c / 100, 2) if isinstance(c, (int, float)) and c > 0 else None


def resumer(p, pays="FR"):
    """Fiche Keepa -> résumé de ≈ 200 octets : ce qu'il faut pour se passer de Keepa plus tard."""
    st = p.get("stats") or {}
    cur, a90, a180 = st.get("current") or [], st.get("avg90") or [], st.get("avg180") or []

    def v(serie, i):
        return _prix(serie[i]) if len(serie) > i else None

    def mn(i):
        try:
            return _prix((st.get("min") or [])[i][1])
        except (IndexError, TypeError):
            return None

    neuf = min([x for x in (v(cur, I_AMAZON), v(cur, I_NEUF)) if x], default=None)
    moy90 = min([x for x in (v(a90, I_AMAZON), v(a90, I_NEUF)) if x], default=None)
    moy180 = min([x for x in (v(a180, I_AMAZON), v(a180, I_NEUF)) if x], default=None)
    rang = cur[I_RANG] if len(cur) > I_RANG and isinstance(cur[I_RANG], int) and cur[I_RANG] > 0 else None
    nb_neuf = cur[I_NB_NEUF] if len(cur) > I_NB_NEUF and isinstance(cur[I_NB_NEUF], int) and cur[I_NB_NEUF] >= 0 else None
    return {
        "asin": p.get("asin"), "ean": (p.get("eanList") or [None])[0], "t": (p.get("title") or "")[:90],
        "marque": (p.get("brand") or "")[:30] or None, "cat": p.get("rootCategory"), "pays": pays,
        "neuf": neuf, "amazon": v(cur, I_AMAZON), "occ": v(cur, I_OCCASION), "wh": v(cur, I_WAREHOUSE),
        "m90": moy90, "m180": moy180, "min90": min([x for x in (mn(I_AMAZON), mn(I_NEUF)) if x], default=None),
        "rang": rang, "ch30": st.get("salesRankDrops30"), "ch90": st.get("salesRankDrops90"),
        "offres": nb_neuf, "note": p.get("reviews", {}).get("rating") if isinstance(p.get("reviews"), dict) else None,
        "vu": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def _garder(resumes):
    """Ajoute les résumés au fichier du mois (gzip) et à l'index (1 ligne par ASIN+pays, la plus récente)."""
    if not resumes:
        return 0
    os.makedirs(D_BASE, exist_ok=True)
    f = os.path.join(D_BASE, datetime.now(timezone.utc).strftime("%Y-%m") + ".jsonl.gz")
    with gzip.open(f, "at", encoding="utf-8") as g:
        for r in resumes:
            g.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    idx = _lire(F_INDEX, {})
    for r in resumes:
        if r.get("asin"):
            idx[f'{r["asin"]}:{r["pays"]}'] = {k: r.get(k) for k in ("ean", "t", "neuf", "m90", "rang", "ch30", "offres", "vu")}
    _ecrire(F_INDEX, idx, compact=True)
    return len(resumes)


def fiches(asins, pays="FR", etat=None):
    """Fiches complètes de ≤ 100 ASIN en un appel (1 jeton chacune). Renvoie la liste des résumés."""
    asins = [a for a in dict.fromkeys(asins) if a][:100]
    if not asins or (etat is not None and not _peut(len(asins), etat)):
        return []
    d = _appel("product", {"domain": DOMAINES.get(pays, 4), "asin": ",".join(asins), "stats": 180, "history": 0})
    return [resumer(p, pays) for p in (d.get("products") or []) if isinstance(p, dict)]


# ---------- 1. RADAR AMAZON ----------
F_PRIORITE = os.path.join(RACINE, "data/etat/arbitrage_priorite.json")


def radar(etat):
    """Baisses de prix Amazon des dernières 24 h : France (neuf + Seconde main, 3 pages) -> radar ;
    Allemagne / Italie / Espagne (neuf, 1 page) -> file prioritaire de l'arbitrage (le prix France est comparé au tour suivant)."""
    if not _peut(60, etat):
        return 0
    trouves, prioritaires = [], []
    plans = [(4, 1, "neuf", 0), (4, 1, "neuf", 1), (4, 1, "neuf", 2), (4, 9, "seconde_main", 0), (3, 1, "neuf", 0), (8, 1, "neuf", 0), (9, 1, "neuf", 0)]
    for domaine, type_prix, nom, page in plans:
        cats = [c for c, _ in categories_fr()] if domaine == 4 else []
        sel = {"page": page, "domainId": domaine, "priceTypes": [type_prix], "dateRange": 3, "isFilterEnabled": True, "isRangeEnabled": True,
               "deltaPercentRange": [20, 95], "currentRange": [PRIX_MIN_CENT, PRIX_MAX_CENT], "salesRankRange": [1, 80000],
               "singleVariation": True, "filterErotic": True, "hasReviews": True,
               **({"includeCategories": cats[:500]} if cats and cats != [c for c, _ in CATEGORIES_FR] else {})}
        try:
            d = _appel("deal", {"domain": domaine}, corps=sel)
        except Exception as e:
            sante.noter("erreur", "moisson radar", f"{nom} {domaine} p{page}: {type(e).__name__}: {str(e)[:120]}")
            continue
        dr = (d.get("deals") or {}).get("dr") or []
        if domaine != 4:
            prioritaires += [x.get("asin") for x in dr if x.get("asin")]
            continue
        for x in dr:
            cur, delta_pct, avg = x.get("current") or [], x.get("deltaPercent") or [], x.get("avg") or []
            prix = _prix(cur[type_prix]) if len(cur) > type_prix else None
            if not prix:
                continue
            try:  # avg[intervalle][type] ; 2 = mois, 3 = 90 jours (-1/-2 = inconnu)
                moy_mois, moy_90 = _prix(avg[2][type_prix]), _prix(avg[3][type_prix])
            except (IndexError, TypeError):
                moy_mois = moy_90 = None
            ref = moy_90 or moy_mois
            baisse = round((ref - prix) / ref * 100) if ref and ref > prix else None  # calculée par nous, jamais par le champ delta
            if not baisse or baisse < 15:
                continue  # pas une vraie baisse (le prix du jour n'est pas sous la moyenne)
            rang = cur[I_RANG] if len(cur) > I_RANG and isinstance(cur[I_RANG], int) and cur[I_RANG] > 0 else None
            trouves.append({"asin": x.get("asin"), "titre": (x.get("title") or "")[:100], "type": nom, "prix": prix,
                            "moyenne_mois": moy_mois, "moyenne_90j": moy_90, "baisse_pct": baisse,
                            "rang": rang, "etat_seconde_main": x.get("warehouseCondition"),
                            "lien": f"https://www.amazon.fr/dp/{x.get('asin')}", "vu": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")})
    if prioritaires:
        anc = _lire(F_PRIORITE, [])
        _ecrire(F_PRIORITE, list(dict.fromkeys(anc + prioritaires))[-600:], compact=True)
    if trouves:
        anciens = _lire(F_RADAR, {}).get("affaires", [])
        deja = {a["asin"] + a["type"] for a in trouves}
        garde = [a for a in anciens if a["asin"] + a["type"] not in deja and a.get("vu", "")[:10] >= (datetime.now(timezone.utc).strftime("%Y-%m-%d"))]
        tout = sorted(trouves + garde, key=lambda a: -(a.get("baisse_pct") or 0))[:400]
        _ecrire(F_RADAR, {"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "nb": len(tout), "affaires": tout})
        # les prix observés vont aussi dans la base commune (data/base/prix)
        from . import base
        for a in trouves:
            base.noter_prix(a["titre"], a["prix"], pays="FR", site="amazon.fr", lien=a["lien"], source="keepa-radar", denicheur="A",
                            etat="neuf" if a["type"] == "neuf" else "occasion")
        base.sauver()
    return len(trouves)


# ---------- 2. ÉTAGÈRE (notre base) ----------
# grandes catégories Amazon.fr (identifiants de nœuds racine) : ce qu'on sait revendre
CATEGORIES_FR = [
    (13921051, "High-tech"), (340858031, "Informatique"), (57004031, "Cuisine & Maison"), (325614031, "Sports et Loisirs"),
    (322086011, "Jeux et Jouets"), (530490, "Jeux vidéo"), (197858031, "Bricolage"), (1571271031, "Jardin"),
    (215934031, "Beauté"), (11961521, "Vêtements"), (206120031, "Bébés & Puériculture"), (1571264031, "Auto et Moto"),
    (2036923031, "Animalerie"), (13921051, "High-tech (2e tour)"),
]


MOTS_CATS = ("high-tech", "informatique", "cuisine", "sport", "jouet", "jeux vidéo", "bricolage", "jardin", "beauté",
             "vêtements", "bébé", "auto", "animalerie", "instruments", "bagages", "fournitures")


def categories_fr():
    """Catégories racine Amazon.fr lues sur Keepa (data/base/keepa_categories.json) ; sinon la liste en dur."""
    cats = _lire(F_CATS, {})
    choisies = []
    for ident, c in cats.items():
        nom = (c.get("nom") or "").lower()
        if any(m in nom for m in MOTS_CATS):
            try:
                choisies.append((int(ident), c.get("nom")))
            except ValueError:
                pass
    return sorted(choisies) or CATEGORIES_FR


def etagere(etat, nb_cats=4):
    """Pour quelques catégories (en rotation) : les 100 produits qui se vendent le plus en ce moment, fiche complète."""
    total = 0
    cats = categories_fr()
    for _ in range(nb_cats):
        if not _peut(115, etat):
            break
        i = etat.get("cat_suivante", 0) % len(cats)
        etat["cat_suivante"] = i + 1
        cat_id, cat_nom = cats[i]
        sel = {"rootCategory": [cat_id], "current_NEW_gte": PRIX_MIN_CENT, "current_NEW_lte": PRIX_MAX_CENT,
               "salesRankDrops30_gte": 25, "productType": 0, "perPage": 100, "page": etat["tours"] % 3,
               "sort": [["salesRankDrops30", "desc"]]}
        try:
            d = _appel("query", {"domain": 4, "selection": json.dumps(sel)})
            asins = d.get("asinList") or []
            res = fiches(asins, "FR")
            for r in res:
                r["etagere"] = cat_nom
            total += _garder(res)
        except Exception as e:
            sante.noter("erreur", "moisson étagère", f"{cat_nom}: {type(e).__name__}: {str(e)[:120]}")
    return total


# ---------- 3. HYPE ÉTRANGÈRE ----------
# identifiants des catégories racine (lus sur Keepa le 04/11/2026) : les noms de groupe renvoient une liste vide
CATEGORIES_HYPE = {
    "US": [(172282, "High-tech"), (165793011, "Jouets"), (1055398, "Maison"), (3375251, "Sport"), (3760911, "Beauté"),
           (228013, "Bricolage"), (468642, "Jeux vidéo"), (2335752011, "Téléphonie"), (165796011, "Bébé"), (2619533011, "Animaux")],
    "JP": [(3210981, "High-tech"), (13299531, "Jouets"), (3828871, "Maison"), (52374051, "Beauté"), (637394, "Jeux vidéo"),
           (14304371, "Sport"), (2127209051, "Informatique"), (2277721051, "Hobby")],
}


def _international(titre):
    """Un produit japonais n'est intéressant que si son titre est lisible ici (marque mondiale) : ≥ 60 % de lettres latines."""
    lettres = [c for c in (titre or "") if c.isalpha()]
    return bool(lettres) and sum(1 for c in lettres if c.isascii()) / len(lettres) >= 0.6


def hype(etat):
    """Meilleures ventes d'une catégorie aux USA ou au Japon (50 jetons), fiche des 100 premiers là-bas (100 jetons),
    puis regard sur Amazon.fr (100 jetons) : ce qui cartonne là-bas et n'existe pas / se vend mal en France."""
    if not _peut(260, etat):
        return 0
    pays = PAYS_HYPE[etat.get("pays_suivant", 0) % len(PAYS_HYPE)]
    etat["pays_suivant"] = etat.get("pays_suivant", 0) + 1
    cats = CATEGORIES_HYPE[pays]
    i = etat.get("hype_suivante", 0) % len(cats)
    etat["hype_suivante"] = i + 1
    cat, cat_fr = cats[i]
    try:
        d = _appel("bestsellers", {"domain": DOMAINES[pays], "category": cat})
        asins = ((d.get("bestSellersList") or {}).get("asinList") or [])[:100]
        if not asins:
            sante.noter("erreur", "moisson hype", f"{pays} {cat_fr} : liste des meilleures ventes vide")
        if not asins:
            return 0
        labas = {r["asin"]: r for r in fiches(asins, pays)}
        ici = {r["asin"]: r for r in fiches(list(labas), "FR")}
    except Exception as e:
        sante.noter("erreur", "moisson hype", f"{pays} {cat}: {type(e).__name__}: {str(e)[:120]}")
        return 0
    trouves = []
    for rang_labas, asin in enumerate(asins, 1):
        a, b = labas.get(asin), ici.get(asin)
        if not a or (pays == "JP" and not _international(a.get("t"))):
            continue
        absent = not b or not b.get("neuf")
        faible = bool(b and b.get("rang") and b["rang"] > 20000)
        if absent or faible:
            trouves.append({"asin": asin, "titre": a.get("t"), "marque": a.get("marque"), "pays": pays, "categorie": cat_fr,
                            "rang_labas": rang_labas, "ventes_30j_labas": a.get("ch30"), "prix_labas": a.get("neuf"),
                            "en_france": "absent" if absent else "mal vendu", "prix_fr": (b or {}).get("neuf"), "rang_fr": (b or {}).get("rang"),
                            "lien_fr": f"https://www.amazon.fr/dp/{asin}", "vu": datetime.now(timezone.utc).strftime("%Y-%m-%d")})
    _garder([r for r in labas.values()] + [r for r in ici.values()])
    h = _lire(F_HYPE, {"produits": []})
    deja = {x["asin"] for x in trouves}
    anciens = [x for x in h.get("produits", []) if x["asin"] not in deja][-600:]
    h = {"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "produits": anciens + trouves}
    _ecrire(F_HYPE, h)
    return len(trouves)


def annonces_radar(maxi=60):
    """Les baisses Amazon du radar, au format des annonces des autres sources (pour le passage et l'équipe)."""
    out = []
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for a in _lire(F_RADAR, {}).get("affaires", []):
        if (a.get("vu") or "")[:10] != jour or not a.get("prix"):
            continue
        etat = "" if a["type"] == "neuf" else " [Seconde main Amazon]"
        out.append({"id": f'keepa-{a["asin"]}-{a["type"]}', "titre": (a.get("titre") or "") + etat,
                    "temperature": min(int((a.get("baisse_pct") or 0) * 8), 900), "categorie": "Amazon",
                    "marchand": "Amazon.fr", "prix": a["prix"], "devise": "EUR", "lien": a["lien"], "date": a.get("vu", ""),
                    "source": "keepa-radar", "pays": "FR", "asin": a.get("asin"), "ref_fr": a.get("moyenne_90j"),
                    "description": f'moyenne 90 j {a.get("moyenne_90j")} €, baisse {a.get("baisse_pct")} %, rang {a.get("rang")}'})
        if len(out) >= maxi:
            break
    return out


# ---------- tour complet ----------
def tour():
    if not keepa.cle():
        print("moisson : clé Keepa absente")
        return
    etat = _etat()
    if etat["jetons_jour"] >= JETONS_JOUR_MAX:
        print("moisson : plafond du jour atteint")
        return
    debut = jetons_restants()
    bilan = {"jetons_debut": debut}
    bilan["radar"] = sante.protege("moisson radar", radar, etat, defaut=0)
    from . import arbitrage
    bilan["arbitrage"] = sante.protege("moisson arbitrage", arbitrage.tour, etat, defaut=0)
    # la réserve ne se remplit que de ≈ 200 jetons entre deux tours (10 min) : un tour sur trois pour la hype
    # (≈ 250 jetons), les deux autres pour l'étagère ; ce qui reste va à l'autre récolte.
    if etat["tours"] % 3 == 0:
        bilan["hype"] = sante.protege("moisson hype", hype, etat, defaut=0)
        bilan["etagere"] = sante.protege("moisson étagère", etagere, etat, defaut=0)
    else:
        bilan["etagere"] = sante.protege("moisson étagère", etagere, etat, defaut=0)
        bilan["hype"] = sante.protege("moisson hype", hype, etat, defaut=0)
    etat["jetons_jour"] += _jetons["depenses"]
    etat["produits_jour"] = etat.get("produits_jour", 0) + bilan["etagere"]
    etat["tours"] += 1
    etat["dernier"] = {"heure": datetime.now(timezone.utc).isoformat(timespec="minutes"), **bilan,
                       "jetons_depenses": _jetons["depenses"], "jetons_fin": _jetons["restants"]}
    _ecrire(F_ETAT, etat)
    print(f"moisson : {_jetons['depenses']} jetons dépensés ({debut} -> {_jetons['restants']}), "
          f"radar {bilan['radar']} affaires, arbitrage {bilan.get('arbitrage')} écarts, hype {bilan['hype']} produits, étagère {bilan['etagere']} fiches gardées")


if __name__ == "__main__":
    tour()
