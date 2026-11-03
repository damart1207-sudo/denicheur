"""DataForSEO (compte ouvert le 03/11/2026, dépôt de 50 $, paiement à l'usage) : la demande réelle pour Amigo.
- volumes(mots) : volume de recherche mensuel Google France (données Google Ads), 0,09 $ par appel jusqu'à
  1 000 mots-clés (mode live) ;
- tendances(mot, pays) : Google Trends par pays (FR, DE, ES, IT, US…), 0,011 $ par appel (5 mots-clés max) ;
  sert au « décalage de hype » : un produit qui monte en Allemagne ou aux USA avant la France.

Garde-fou : plafond de dépense par jour (PLAFOND_JOUR_USD), suivi dans data/etat/dataforseo_budget.json.
Identifiants : secrets GitHub DATAFORSEO_LOGIN et DATAFORSEO_PASSWORD (login + mot de passe API, pas ceux du site).
Documentation : https://docs.dataforseo.com/v3/
"""
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_BUDGET = os.path.join(RACINE, "data/etat/dataforseo_budget.json")
PLAFOND_JOUR_USD = 0.70
PAYS = {"FR": 2250, "DE": 2276, "ES": 2724, "IT": 2380, "US": 2840, "UK": 2826, "NL": 2528, "PL": 2616}
LANGUE = {"FR": "fr", "DE": "de", "ES": "es", "IT": "it", "US": "en", "UK": "en", "NL": "nl", "PL": "pl"}
COUT = {"volumes": 0.09, "tendances": 0.011}


def _auth():
    login = os.environ.get("DATAFORSEO_LOGIN", "").strip()
    mdp = os.environ.get("DATAFORSEO_PASSWORD", "").strip()
    if not login or not mdp:
        return None
    return "Basic " + base64.b64encode(f"{login}:{mdp}".encode()).decode()


def _budget():
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        b = json.load(open(F_BUDGET))
    except (OSError, json.JSONDecodeError):
        b = {}
    if b.get("jour") != jour:
        b = {"jour": jour, "depense_usd": 0.0, "appels": 0, "mois": b.get("mois") if b.get("mois", "")[:7] == jour[:7] else jour[:7], "depense_mois_usd": b.get("depense_mois_usd", 0.0) if b.get("mois", "")[:7] == jour[:7] else 0.0}
    return b


def _noter(b, cout):
    b["depense_usd"] = round(b["depense_usd"] + cout, 4)
    b["depense_mois_usd"] = round(b.get("depense_mois_usd", 0.0) + cout, 4)
    b["appels"] += 1
    os.makedirs(os.path.dirname(F_BUDGET), exist_ok=True)
    json.dump(b, open(F_BUDGET, "w"), indent=1)


def disponible(cout=0.1):
    return _auth() is not None and _budget()["depense_usd"] + cout <= PLAFOND_JOUR_USD


def _poster(chemin, taches, cout):
    auth = _auth()
    b = _budget()
    req = urllib.request.Request("https://api.dataforseo.com/v3/" + chemin, data=json.dumps(taches).encode(),
                                 headers={"Authorization": auth, "Content-Type": "application/json", "User-Agent": "denicheur/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        corps = e.read()[:300].decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} : {corps}") from None
    _noter(b, float(d.get("cost") or cout))
    if d.get("status_code") != 20000:
        raise RuntimeError(f"DataForSEO {d.get('status_code')}: {d.get('status_message')}")
    return d.get("tasks") or []


def volumes(mots, pays="FR"):
    """Volume de recherche mensuel Google (Google Ads) pour une liste de mots-clés (≤ 1 000). {mot: {...}}."""
    mots = [m.strip()[:80] for m in mots if m and m.strip()][:1000]
    if not mots or not disponible(COUT["volumes"]):
        return {}
    taches = _poster("keywords_data/google_ads/search_volume/live",
                     [{"keywords": mots, "location_code": PAYS.get(pays, 2250), "language_code": LANGUE.get(pays, "fr")}],
                     COUT["volumes"])
    res = {}
    for t in taches:
        for it in (t.get("result") or []):
            if not isinstance(it, dict) or not it.get("keyword"):
                continue
            hist = [h.get("search_volume") or 0 for h in (it.get("monthly_searches") or [])[:3]]
            res[it["keyword"]] = {"volume_mensuel": it.get("search_volume"), "concurrence": it.get("competition"),
                                  "cpc": it.get("cpc"), "trois_derniers_mois": hist}
    return res


def tendances(mots, pays="FR", periode="past_90_days"):
    """Google Trends : intérêt 0-100 dans le temps pour ≤ 5 mots-clés dans un pays. {mot: {"serie": [...], "actuel", "moyenne", "tendance"}}."""
    mots = [m.strip()[:80] for m in mots if m and m.strip()][:5]
    if not mots or not disponible(COUT["tendances"]):
        return {}
    taches = _poster("keywords_data/google_trends/explore/live",
                     [{"keywords": mots, "location_code": PAYS.get(pays, 2250), "language_code": LANGUE.get(pays, "fr"),
                       "type": "web", "time_range": periode, "item_types": ["google_trends_graph"]}],
                     COUT["tendances"])
    res = {}
    for t in taches:
        for r in (t.get("result") or []):
            for item in (r.get("items") or []):
                if item.get("type") != "google_trends_graph":
                    continue
                noms = item.get("keywords") or mots
                data = item.get("data") or []
                for i, mot in enumerate(noms):
                    serie = [(pt.get("values") or [None] * (i + 1))[i] for pt in data]
                    serie = [v if isinstance(v, (int, float)) else 0 for v in serie]
                    if not serie:
                        continue
                    n = max(1, len(serie) // 4)
                    debut, fin = sum(serie[:n]) / n, sum(serie[-n:]) / n
                    res[mot] = {"serie": serie, "actuel": serie[-1], "moyenne": round(sum(serie) / len(serie), 1),
                                "tendance": "monte" if fin > debut * 1.3 else "baisse" if fin < debut * 0.7 else "stable",
                                "pays": pays}
    return res


def decalage_hype(mot, pays_avance=("US", "DE", "ES"), pays_cible="FR"):
    """Le produit monte-t-il ailleurs avant la France ? Renvoie {pays: tendance} + verdict."""
    res = {"mot": mot, "pays": {}}
    for p in list(pays_avance) + [pays_cible]:
        t = tendances([mot], p)
        if mot in t:
            res["pays"][p] = {"tendance": t[mot]["tendance"], "actuel": t[mot]["actuel"], "moyenne": t[mot]["moyenne"]}
    cible = res["pays"].get(pays_cible, {}).get("tendance")
    ailleurs = [p for p in pays_avance if res["pays"].get(p, {}).get("tendance") == "monte"]
    res["verdict"] = "vague à venir en France" if ailleurs and cible in ("stable", "baisse") else \
                     "déjà en France" if cible == "monte" else "rien de notable"
    res["monte_dans"] = ailleurs
    return res
