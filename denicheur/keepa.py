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
APPELS_JOUR_MAX = 600          # 20 jetons/min = 28 800/jour possibles ; on reste très en dessous
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
    attente = 3.1 - (time.time() - _dernier[0])  # 20 jetons/min : 1 appel toutes les 3 s
    if attente > 0:
        time.sleep(attente)
    _dernier[0] = time.time()
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "denicheur/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


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
    p = prods[0]
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
    pays_code = next((k for k, v in DOMAINES.items() if v == params["domain"]), pays)
    return {
        "asin": p.get("asin"), "titre": p.get("title"), "ean": (p.get("eanList") or [None])[0], "pays": pays_code,
        "prix_neuf": prix_neuf, "prix_amazon": cur_am, "prix_tiers": cur_neuf,
        "moyenne_90j": moy90, "plus_bas_90j": min90,
        "occasion": _prix(cur[I_OCCASION]) if len(cur) > I_OCCASION else None,
        "rang_ventes": rang, "chutes_rang_30j": chutes30, "chutes_rang_90j": chutes90,
        "ventes_estimees_30j": chutes30,  # une chute de classement ≈ une vente (approximation utilisée par les pros)
        "remise_sincere": sincere,
        "lien": f"https://www.amazon.{ 'fr' if pays_code == 'FR' else 'de' if pays_code == 'DE' else 'it' if pays_code == 'IT' else 'es' if pays_code == 'ES' else 'com'}/dp/{p.get('asin')}",
        "jetons_restants": d.get("tokensLeft"),
    }


def comparer_pays(ean, pays=("FR", "DE", "IT", "ES")):
    """Prix neuf Amazon par pays pour un EAN : repère où acheter (le moins cher) et où vendre (le plus cher)."""
    res = {}
    for p in pays:
        f = fiche(ean=ean, pays=p)
        if f and f.get("prix_neuf"):
            res[p] = f["prix_neuf"]
    return res
