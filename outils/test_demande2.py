import json, os, re, urllib.parse, urllib.request
T = os.environ.get("APIFY_TOKEN", "").strip()
UA = {"User-Agent": "Mozilla/5.0 Chrome/130.0", "Accept-Language": "fr-FR"}
res = {}
def lire(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")
for c in range(1, 21):
    try:
        h = lire(f"https://trends.google.com/trending/rss?geo=FR&category={c}")
        res[f"trends_cat_{c}"] = re.findall(r"<title>(.*?)</title>", h)[1:7]
    except Exception as e:
        res[f"trends_cat_{c}"] = str(e)[:80]
def api(chemin, corps=None, params=None):
    url = "https://api.apify.com/v2" + chemin + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, data=json.dumps(corps).encode() if corps is not None else None, method="POST" if corps is not None else "GET",
                                 headers={"Authorization": f"Bearer {T}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=200) as r:
        return json.loads(r.read() or b"null")
for acteur, entree in (("saswave~idealo-trending-search-scraper", {"domains": ["idealo.fr"]}),
                       ("junglee~amazon-bestsellers", {"categoryUrls": [{"url": "https://www.amazon.fr/gp/movers-and-shakers"}], "maxItemsPerStartUrl": 20, "depthOfCrawl": 1})):
    try:
        act = api(f"/acts/{acteur}")["data"]
        b = act.get("taggedBuilds", {}).get("latest", {}).get("buildId")
        sch = api(f"/acts/{acteur}/builds/{b}")["data"].get("inputSchema")
        sch = json.loads(sch) if isinstance(sch, str) else sch
        res[acteur + "_schema"] = {k: str(v.get("prefill", v.get("default")))[:100] for k, v in (sch or {}).get("properties", {}).items()}
        it = api(f"/acts/{acteur}/run-sync-get-dataset-items", entree, {"timeout": 150, "maxItems": 25, "maxTotalChargeUsd": 0.05})
        res[acteur] = {"nb": len(it), "exemples": [json.dumps(i, ensure_ascii=False)[:220] for i in it[:12]]}
    except urllib.error.HTTPError as e:
        res[acteur] = f"HTTP {e.code}: {e.read()[:250].decode(errors='replace')}"
    except Exception as e:
        res[acteur] = str(e)[:200]
json.dump(res, open("data/test_demande2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
