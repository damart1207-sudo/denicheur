"""Keepa (abonnement Data Access pris le 03/11/2026, 20 jetons/minute) : Amazon France, Allemagne, Italie,
Espagne, Pologne. Pour un produit (code EAN ou ASIN) :
- prix neuf actuel (Amazon ou vendeur tiers), plus bas et moyenne sur 90 jours ;
- « remise sincère » : le prix du jour est-il vraiment sous la médiane/moyenne des 90 derniers jours,
  sans hausse artificielle juste avant (technique des faux « prix barrés ») ;
- compteur de ventes : chutes du classement des ventes sur 30 et 90 jours (méthode japonaise « sedori »).

Garde-fous : plafond d'appels par jour (data/etat/keepa_budget.json), 1 jeton par produit, aucun achat.
Documentation : https://keepa.com/#!discuss/t/product-object/116
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_BUDGET = os.path.join(RACINE, "data/etat/keepa_budget.json")
APPELS_JOUR_MAX = 3000         # fiches/recherches du passage et de la veille (le moissonneur a son propre compteur)
DOMAINES = {"FR": 4, "DE": 3, "IT": 8, "ES": 9, "UK": 2, "US": 1, "NL": 14, "PL": 17}
URL = "https://api.keepa.com/product"
# index des séries Keepa (stats.current / avg90 / min / max)
I_AMAZON, I_NEUF, I_OCCASION, I_RANG = 0, 1, 2, 3
_dernier = [0.0]


def cle():
    return os.environ.get("KEEPA_API_KEY", "").strip()


def _budget():
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        b = json.load(open(F_BUDGET))
    except (OSError, json.JSONDecodeError):
        b = {}
    if b.get("jour") != jour:
        b = {"jour": jour, "appels": 0, "jetons_restants": None}
    return b


def _noter(b, jetons=None):
    b["appels"] += 1
    if jetons is not None:
        b["jetons_restants"] = jetons
    os.makedirs(os.path.dirname(F_BUDGET), exist_ok=True)
    json.dump(b, open(F_BUDGET, "w"), indent=1)


def disponible():
    return bool(cle()) and _budget()["appels"] < APPELS_JOUR_MAX


def _prix(centimes):
    return round(centimes / 100, 2) if isinstance(centimes, (int, float)) and centimes > 0 else None


def _lire(params):
    return _lire_url(URL, params)


def _lire_url(url, params):
    attente = 1.1 - (time.time() - _dernier[0])  # politesse ; le vrai rythme est donné par la réserve de jetons
    if attente > 0:
        time.sleep(attente)
    _dernier[0] = time.time()
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "denicheur/1.0", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=40) as r:
        brut = r.read()
    if brut[:2] == b"\x1f\x8b":  # Keepa répond toujours compressé (gzip)
        import gzip
        brut = gzip.decompress(brut)
    return json.loads(brut)


def fiche(ean=None, asin=None, pays="FR"):
    """Renvoie la fiche Amazon d'un produit (dict) ou None. 1 jeton Keepa."""
    if not disponible() or not (ean or asin):
        return None
    b = _budget()
    params = {"key": cle(), "domain": DOMAINES.get(pays, 4), "stats": 90, "history": 0}
    if asin:
        params["asin"] = asin
    else:
        params["code"] = str(ean).strip()
    try:
        d = _lire(params)
    except Exception as e:
        _noter(b)
        return {"erreur": f"{type(e).__name__}: {str(e)[:80]}"}
    _noter(b, d.get("tokensLeft"))
    prods = d.get("products") or []
    if not prods:
        return None
    # Un résultat de recherche/code n'est pas une preuve d'identité : certains
    # retours contiennent plusieurs produits. Ne jamais prendre le premier.
    def identique(p):
        if not isinstance(p, dict):
            return False
        if asin:
            return str(p.get('asin', '')).upper() == str(asin).strip().upper()
        demande = str(ean).strip()
        if not demande.isdigit() or len(demande) not in (8, 12, 13, 14):
            return False
        codes = [code for champ in ('eanList', 'upcList')
                 for code in (p.get(champ) if isinstance(p.get(champ), list) else [])]
        return any(str(c).isdigit() and str(c).zfill(14) == demande.zfill(14) for c in codes)
    exacts = [p for p in prods if identique(p)]
    if len(exacts) != 1:
        return None
    return _parser(exacts[0], params["domain"], pays, d.get("tokensLeft"))


def _parser(p, domaine, pays="FR", jetons=None):
    """Produit Keepa (objet brut) -> fiche lisible."""
    st = p.get("stats") or {}
    cur, avg90, mn = st.get("current") or [], st.get("avg90") or [], st.get("min") or []
    cur_am, cur_neuf = _prix(cur[I_AMAZON]) if len(cur) > I_AMAZON else None, _prix(cur[I_NEUF]) if len(cur) > I_NEUF else None
    prix_neuf = min([x for x in (cur_am, cur_neuf) if x], default=None)
    moy90 = min([x for x in (_prix(avg90[I_AMAZON]) if len(avg90) > I_AMAZON else None,
                             _prix(avg90[I_NEUF]) if len(avg90) > I_NEUF else None) if x], default=None)
    # stats.min = [[date, prix], ...] par série ; on garde le prix
    def _min(i):
        try:
            return _prix(mn[i][1])
        except (IndexError, TypeError):
            return None
    min90 = min([x for x in (_min(I_AMAZON), _min(I_NEUF)) if x], default=None)
    rang = cur[I_RANG] if len(cur) > I_RANG and isinstance(cur[I_RANG], int) and cur[I_RANG] > 0 else None
    chutes30, chutes90 = st.get("salesRankDrops30"), st.get("salesRankDrops90")
    sincere = None
    if prix_neuf and moy90:
        sincere = prix_neuf <= moy90 * 0.95  # vraie baisse : au moins 5 % sous la moyenne des 90 derniers jours
    pays_code = next((k for k, v in DOMAINES.items() if v == domaine), pays)
    nb_neuf = cur[11] if len(cur) > 11 and isinstance(cur[11], int) and cur[11] >= 0 else None
    return {
        "nb_vendeurs_neuf": nb_neuf,  # concurrence sur Amazon (offres neuves en cours)
        "marque": p.get("brand"),
        "asin": p.get("asin"), "titre": p.get("title"), "ean": (p.get("eanList") or [None])[0], "pays": pays_code,
        "prix_neuf": prix_neuf, "prix_amazon": cur_am, "prix_tiers": cur_neuf,
        "moyenne_90j": moy90, "plus_bas_90j": min90,
        "occasion": _prix(cur[I_OCCASION]) if len(cur) > I_OCCASION else None,
        "rang_ventes": rang, "chutes_rang_30j": chutes30, "chutes_rang_90j": chutes90,
        "ventes_estimees_30j": chutes30,  # une chute de classement ≈ une vente (approximation utilisée par les pros)
        "remise_sincere": sincere,
        "lien": f"https://www.amazon.{ 'fr' if pays_code == 'FR' else 'de' if pays_code == 'DE' else 'it' if pays_code == 'IT' else 'es' if pays_code == 'ES' else 'com'}/dp/{p.get('asin')}",
        "jetons_restants": jetons,
    }


def vendeurs(asin, pays="FR", maxi=10):
    """Les vendeurs actuels d'un produit Amazon (offres en direct, 6 jetons par page de 10) + fiche de chaque vendeur
    (1 jeton : nom, pays, raison sociale). Sert au Sourceur : qui vend le moins cher, d'où il vient, comment il se fournit."""
    if not disponible() or not asin:
        return []
    b = _budget()
    try:
        d = _lire({"key": cle(), "domain": DOMAINES.get(pays, 4), "asin": asin, "offers": 20, "history": 0, "stats": 0})
    except Exception as e:
        _noter(b)
        return [{"erreur": f"{type(e).__name__}: {str(e)[:80]}"}]
    _noter(b, d.get("tokensLeft"))
    prods = d.get("products") or []
    if not prods:
        return []
    offres = []
    for o in (prods[0].get("offers") or []):
        if not isinstance(o, dict):
            continue
        hist = o.get("offerCSV") or []
        prix = _prix(hist[-2]) if len(hist) >= 2 else None  # dernier [date, prix, port]
        port = _prix(hist[-1]) if len(hist) >= 1 and isinstance(hist[-1], (int, float)) and hist[-1] > 0 else 0.0
        offres.append({"sellerId": o.get("sellerId"), "prix": prix, "port": port, "etat": o.get("condition"), "fba": o.get("isFBA"),
                       "prime": o.get("isPrime"), "amazon": o.get("isAmazon"), "entrepot": o.get("isWarehouseDeal")})
    offres = [o for o in offres if o["prix"] and o.get("etat") in (None, 1)]  # 1 = neuf
    offres.sort(key=lambda o: o["prix"] + (o["port"] or 0))
    out = []
    for o in offres[:maxi]:
        sid = o["sellerId"]
        nom, pays_v, societe = ("Amazon", "FR", "Amazon") if o.get("amazon") else (None, None, None)
        if sid and not o.get("amazon") and disponible():
            try:
                ds = _lire_url("https://api.keepa.com/seller", {"key": cle(), "domain": DOMAINES.get(pays, 4), "seller": sid})
                _noter(_budget(), ds.get("tokensLeft"))
                sv = (ds.get("sellers") or {}).get(sid) or {}
                nom = sv.get("sellerName")
                adr = sv.get("address") or []
                pays_v = adr[-1] if isinstance(adr, list) and adr else None
                societe = sv.get("businessName")
            except Exception:
                pass
        out.append({**o, "vendeur": nom, "societe": societe, "pays": pays_v, "lien": f"https://www.amazon.fr/sp?seller={sid}" if sid else None})
    return out


def rechercher(nom, pays="FR", prix_attendu=None):
    """Trouve le produit sur Amazon par son NOM (recherche Keepa, 10 jetons) : ASIN, EAN, prix, ventes.
    Garde le meilleur résultat dont le titre correspond au nom (et, si connu, dont le prix est plausible)."""
    if not nom or not disponible():
        return None
    from . import comparateurs
    b = _budget()
    params = {"key": cle(), "domain": DOMAINES.get(pays, 4), "type": "product", "term": nom[:100], "stats": 90, "history": 0}
    try:
        d = _lire_url("https://api.keepa.com/search", params)
    except Exception as e:
        _noter(b)
        return {"erreur": f"{type(e).__name__}: {str(e)[:80]}"}
    _noter(b, d.get("tokensLeft"))
    bons = []
    for p in (d.get("products") or [])[:10]:
        if not isinstance(p, dict) or not comparateurs.correspond(p.get("title") or "", nom):
            continue
        f = _parser(p, params["domain"], pays, d.get("tokensLeft"))
        if prix_attendu and f.get("prix_neuf") and not (0.4 * prix_attendu <= f["prix_neuf"] <= 4 * prix_attendu):
            continue  # un accessoire ou un lot, pas le produit
        bons.append(f)
    if not bons:
        return None
    # le plus vendu d'abord (chutes de classement), puis le mieux classé
    bons.sort(key=lambda f: (-(f.get("chutes_rang_30j") or 0), f.get("rang_ventes") or 10**9))
    return bons[0]


def comparer_pays(ean, pays=("FR", "DE", "IT", "ES")):
    """Prix neuf Amazon par pays pour un EAN : repère où acheter (le moins cher) et où vendre (le plus cher)."""
    res = {}
    for p in pays:
        f = fiche(ean=ean, pays=p)
        if f and f.get("prix_neuf"):
            res[p] = f["prix_neuf"]
    return res
