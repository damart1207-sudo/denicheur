"""Étape 2 : petit test réel de chaque robot. Plafond 0,05 $ par robot (maxTotalChargeUsd), 5-10 résultats."""
import json
import os
import time
import urllib.parse
import urllib.request

TOKEN = os.environ["APIFY_TOKEN"].strip()
Q = "garmin forerunner 165"
TESTS = {
    "idealo_pricepirate": ("pricepirate~idealo-price-data-api", {"operation": "search-by-term", "values": [Q], "country": "fr"}),
    "idealo_memo23": ("memo23~idealo-scraper", {"searchQuery": Q, "country": "FR", "maxItems": 5, "fetchOffers": True}),
    "leboncoin": ("fatihtahta~leboncoin-fr-scraper", {"startUrls": ["https://www.leboncoin.fr/recherche?text=" + urllib.parse.quote(Q)], "limit": 10}),
    "vinted_badger": ("scrape.badger~vinted-scraper", {"mode": "Search Items", "query": Q, "market": "fr", "max_results": 10}),
    "vinted_vendus_kazkn": ("kazkn~vinted-smart-scraper", {"mode": "SOLD_ITEMS", "query": Q, "countries": ["fr"], "maxItems": 10}),
    "kleinanzeigen": ("memo23~kleinanzeigen-search-scraper-ppe", {"searchQueries": [Q], "maxItems": 10, "startUrls": []}),
    "google_shopping": ("damilo~google-shopping-apify", {"query": Q, "country": "fr", "language": "fr", "num": "10"}),
    "chine_1688": ("zen-studio~1688-wholesale-scraper", {"keywords": ["跑步手表"], "maxResults": 5, "sortBy": "bestSelling"}),
    "japon_mercari": ("fatihtahta~mercari-japan-scraper", {"searchQueries": ["ポケモンカード"], "keywords": ["ポケモンカード"], "query": "ポケモンカード", "limit": 5, "maxItems": 5}),
}


def appel(methode, chemin, corps=None, params=None):
    url = "https://api.apify.com/v2" + chemin + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(corps).encode() if corps is not None else None
    req = urllib.request.Request(url, data=data, method=methode, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=200) as r:
        return json.loads(r.read() or b"null")


res = {}
for nom, (acteur, entree) in TESTS.items():
    t0 = time.time()
    try:
        items = appel("POST", f"/acts/{acteur}/run-sync-get-dataset-items", entree,
                      {"timeout": 150, "maxItems": 10, "maxTotalChargeUsd": 0.05})
        items = items if isinstance(items, list) else [items]
        res[nom] = {"ok": True, "nb": len(items), "secondes": round(time.time() - t0),
                    "champs": sorted(items[0].keys())[:40] if items and isinstance(items[0], dict) else None,
                    "exemples": [json.dumps(i, ensure_ascii=False)[:700] for i in items[:3]]}
    except urllib.error.HTTPError as e:
        res[nom] = {"ok": False, "erreur": f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"}
    except Exception as e:
        res[nom] = {"ok": False, "erreur": f"{type(e).__name__}: {str(e)[:200]}"}
    print(nom, res[nom].get("ok"), res[nom].get("nb"), res[nom].get("erreur", "")[:150])
try:
    lim = appel("GET", "/users/me/limits")["data"]
    res["_credit"] = {"limite_usd": lim["limits"]["maxMonthlyUsageUsd"], "utilise_usd": lim["current"]["monthlyUsageUsd"]}
except Exception as e:
    res["_credit"] = {"erreur": str(e)[:150]}
print("credit", res["_credit"])
with open("data/test_apify_reel.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
