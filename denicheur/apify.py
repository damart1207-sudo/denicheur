"""Robots Apify (testés le 01/11/2026) : idealo, Leboncoin, Vinted. Budget plafonné.

Garde-fous : plafond par appel (maxTotalChargeUsd), et budget mensuel suivi dans data/etat/apify_budget.json :
au-delà de BUDGET_MOIS_USD (4 $ sur les 5 $ offerts), plus aucun appel jusqu'au mois suivant.
"""
import json
import os
import re
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import comparateurs

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUDGET_MOIS_USD = 4.0
F_BUDGET = os.path.join(RACINE, "data/etat/apify_budget.json")
ROBOTS = {
    "idealo": ("memo23~idealo-scraper", 0.03),
    "leboncoin": ("fatihtahta~leboncoin-fr-scraper", 0.03),
    "vinted": ("scrape.badger~vinted-scraper", 0.03),
}


def _budget():
    mois = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        b = json.load(open(F_BUDGET))
    except (OSError, json.JSONDecodeError):
        b = {}
    if b.get("mois") != mois:
        b = {"mois": mois, "depense_estimee_usd": 0.0, "appels": 0}
    return b


def _noter(b, cout):
    b["depense_estimee_usd"] = round(b["depense_estimee_usd"] + cout, 4)
    b["depense_ce_tour"] = round(b.get("depense_ce_tour", 0) + cout, 4)
    b["depense_reelle_usd"] = _reel.get("usd")
    b["appels"] += 1
    os.makedirs(os.path.dirname(F_BUDGET), exist_ok=True)
    json.dump(b, open(F_BUDGET, "w"), indent=1)


_reel = {}


def depense_reelle():
    """Dépense réelle du mois lue chez Apify (appel gratuit), une fois par lancement."""
    if "usd" not in _reel:
        try:
            req = urllib.request.Request("https://api.apify.com/v2/users/me/limits",
                                         headers={"Authorization": f"Bearer {os.environ['APIFY_TOKEN'].strip()}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                _reel["usd"] = float(json.loads(r.read())["data"]["current"]["monthlyUsageUsd"])
        except Exception:
            _reel["usd"] = None
    return _reel["usd"]


def disponible():
    if not os.environ.get("APIFY_TOKEN", "").strip():
        return False
    reel = depense_reelle()
    if reel is None:  # impossible de lire la dépense : prudence, on s'arrête
        return False
    return reel + _budget().get("depense_ce_tour", 0) < BUDGET_MOIS_USD


def lancer(robot, entree, maxi=10):
    """Lance un robot (synchrone). Renvoie la liste des résultats, ou None si budget/jeton absent ou erreur."""
    if not disponible():
        return None
    acteur, plafond = ROBOTS[robot]
    b = _budget()
    url = (f"https://api.apify.com/v2/acts/{acteur}/run-sync-get-dataset-items?"
           + urllib.parse.urlencode({"timeout": 150, "maxItems": maxi, "maxTotalChargeUsd": plafond}))
    req = urllib.request.Request(url, data=json.dumps(entree).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ['APIFY_TOKEN'].strip()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=200) as r:
            items = json.loads(r.read() or b"[]")
    except Exception:
        items = None
    _noter(b, plafond)  # on compte le plafond (estimation prudente)
    return items if isinstance(items, list) else None


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d[\d\s.,]*", str(v or ""))
    return comparateurs._prix(m.group(0)) if m else None


def prix_idealo(nom):
    """Prix neuf le plus bas en France sur idealo pour CE produit exact."""
    items = lancer("idealo", {"searchQuery": nom, "country": "FR", "maxItems": 3, "fetchOffers": False}, maxi=3)
    if not items:
        return None
    bons = [i for i in items if isinstance(i, dict) and i.get("price") and comparateurs.correspond(i.get("title", ""), nom)]
    if not bons:
        return None
    b = min(bons, key=lambda i: i["price"])
    return {"prix_min": float(b["price"]), "nb_offres": b.get("offerCount"), "lien": b.get("url"), "titre": b.get("title"),
            "gtin": b.get("gtin")}


def revente_reelle(nom, prix_achat, avec_liens=False):
    """Prix des annonces réelles en cours (neuf ou comme neuf) sur Vinted et Leboncoin."""
    res = {}
    v = lancer("vinted", {"mode": "Search Items", "query": nom, "market": "fr", "max_results": 15}, maxi=15) or []
    pv = [float(i["price_amount"]) for i in v if isinstance(i, dict) and i.get("price_amount")
          and comparateurs.correspond(i.get("title", ""), nom) and "neuf" in (i.get("status") or "").lower()]
    pv = [p for p in pv if p >= prix_achat * 0.5]
    if pv:
        res["vinted"] = {"nb": len(pv), "min": min(pv), "mediane": statistics.median(pv),
                         "lien_min": next((i.get("url") for i in v if isinstance(i, dict) and i.get("price_amount") and float(i["price_amount"]) == min(pv)), None)}
    lb = lancer("leboncoin", {"startUrls": ["https://www.leboncoin.fr/recherche?text=" + urllib.parse.quote(nom)], "limit": 15}, maxi=15) or []
    pl = []
    for i in lb:
        if isinstance(i, dict) and comparateurs.correspond(i.get("title", ""), nom):
            m = re.search(r'"(?:price|amount|value)[a-z_]*"\s*:\s*\[?\s*"?(\d+(?:[.,]\d+)?)', json.dumps(i.get("pricing") or {}))
            p = _num(m.group(1)) if m else None
            if p and p >= prix_achat * 0.5:
                pl.append(p)
    if pl:
        res["leboncoin"] = {"nb": len(pl), "min": min(pl), "mediane": statistics.median(pl)}
    return res
