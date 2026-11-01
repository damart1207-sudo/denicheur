"""Liste les robots Apify disponibles (API publique du store, sans jeton) pour choisir les plus fiables."""
import json
import urllib.parse
import urllib.request

res = {}
for q in ("idealo", "leboncoin", "vinted", "kleinanzeigen", "wallapop", "subito", "mercari", "1688", "amazon price", "google shopping"):
    url = "https://api.apify.com/v2/store?" + urllib.parse.urlencode({"search": q, "limit": 12})
    with urllib.request.urlopen(url, timeout=30) as r:
        items = json.loads(r.read())["data"]["items"]
    res[q] = [{"id": f'{i.get("username")}/{i.get("name")}', "titre": i.get("title"),
               "users": (i.get("stats") or {}).get("totalUsers"), "users30": (i.get("stats") or {}).get("totalUsers30Days"),
               "note": i.get("actorReviewRating"), "prix": i.get("currentPricingInfo") or i.get("pricingInfos")}
              for i in items]
with open("data/apify_store.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("ok")
