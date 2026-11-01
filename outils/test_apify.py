"""Étape 1 du test Apify : jeton valide ? crédit restant ? schéma d'entrée des robots choisis. Coût : 0 $."""
import json
import os
import urllib.request

TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
ROBOTS = ["pricepirate~idealo-price-data-api", "memo23~idealo-scraper", "fatihtahta~leboncoin-fr-scraper",
          "epicscrapers~vinted-search-scraper", "scrape.badger~vinted-scraper", "kazkn~vinted-smart-scraper",
          "memo23~kleinanzeigen-search-scraper-ppe", "damilo~google-shopping-apify", "zen-studio~1688-wholesale-scraper"]


def get(chemin):
    req = urllib.request.Request("https://api.apify.com/v2" + chemin, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["data"]


res = {"jeton": bool(TOKEN)}
if TOKEN:
    try:
        lim = get("/users/me/limits")
        res["credit"] = {"limite_usd": lim.get("limits", {}).get("maxMonthlyUsageUsd"),
                         "utilise_usd": lim.get("current", {}).get("monthlyUsageUsd")}
    except Exception as e:
        res["credit"] = {"erreur": f"{type(e).__name__}: {str(e)[:120]}"}
    res["robots"] = {}
    for r_ in ROBOTS:
        try:
            act = get(f"/acts/{r_}")
            build = act.get("taggedBuilds", {}).get("latest", {}).get("buildId")
            schema = get(f"/acts/{r_}/builds/{build}").get("inputSchema") if build else None
            if isinstance(schema, str):
                schema = json.loads(schema)
            props = (schema or {}).get("properties", {})
            res["robots"][r_] = {k: {"type": v.get("type"), "titre": v.get("title"), "defaut": v.get("default", v.get("prefill")),
                                     "enum": v.get("enum")} for k, v in props.items()}
        except Exception as e:
            res["robots"][r_] = {"erreur": f"{type(e).__name__}: {str(e)[:120]}"}
with open("data/test_apify.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:1500])
