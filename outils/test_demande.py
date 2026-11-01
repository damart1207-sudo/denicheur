"""Teste les sources de DEMANDE (ce que les gens cherchent). Coût Apify plafonné à 0,10 $."""
import json
import os
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR"}
res = {}


def lire(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


# 1. Google Trends : tendances du moment en France (flux RSS public)
try:
    h = lire("https://trends.google.com/trending/rss?geo=FR")
    titres = re.findall(r"<title>(.*?)</title>", h)[1:21]
    trafic = re.findall(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", h)[:20]
    res["google_trends_rss"] = {"ok": True, "tendances": [f"{t} ({v})" for t, v in zip(titres, trafic)]}
except Exception as e:
    res["google_trends_rss"] = {"ok": False, "erreur": str(e)[:150]}
# 2. Amazon France : meilleures ventes et plus fortes progressions
for nom, u in (("amazon_progressions", "https://www.amazon.fr/gp/movers-and-shakers"), ("amazon_meilleures_ventes", "https://www.amazon.fr/gp/bestsellers")):
    try:
        h = lire(u)
        res[nom] = {"ok": "captcha" not in h.lower(), "taille": len(h), "exemples": re.findall(r'_cDEzb_p13n-sc-css-line-clamp-\d_[^"]*">([^<]{5,90})<', h)[:10]}
    except Exception as e:
        res[nom] = {"ok": False, "erreur": str(e)[:150]}
# 3. Suggestions Google pour un début de recherche (ce que les gens tapent)
try:
    u = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode({"client": "firefox", "hl": "fr", "gl": "fr", "q": "promo "})
    res["suggestions_promo"] = {"ok": True, "liste": json.loads(lire(u))[1]}
except Exception as e:
    res["suggestions_promo"] = {"ok": False, "erreur": str(e)[:150]}
# 4. Apify : recherches tendance sur idealo + annonces « Je recherche » sur Leboncoin
T = os.environ.get("APIFY_TOKEN", "").strip()


def apify(acteur, entree, plafond=0.05, maxi=20):
    url = f"https://api.apify.com/v2/acts/{acteur}/run-sync-get-dataset-items?" + urllib.parse.urlencode({"timeout": 150, "maxItems": maxi, "maxTotalChargeUsd": plafond})
    req = urllib.request.Request(url, data=json.dumps(entree).encode(), method="POST", headers={"Authorization": f"Bearer {T}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=200) as r:
        return json.loads(r.read() or b"[]")


for nom, acteur, entree in (
        ("idealo_tendances", "saswave~idealo-trending-search-scraper", {"country": "fr", "countries": ["fr"], "domain": "idealo.fr"}),
        ("leboncoin_demandes", "fatihtahta~leboncoin-fr-scraper", {"startUrls": ["https://www.leboncoin.fr/recherche?category=17&ad_type=demand"], "limit": 15})):
    try:
        it = apify(acteur, entree)
        res[nom] = {"ok": True, "nb": len(it), "exemples": [json.dumps(i, ensure_ascii=False)[:250] for i in it[:8]]}
    except urllib.error.HTTPError as e:
        res[nom] = {"ok": False, "erreur": f"HTTP {e.code}: {e.read()[:250].decode(errors='replace')}"}
    except Exception as e:
        res[nom] = {"ok": False, "erreur": str(e)[:150]}
with open("data/test_demande.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("ok")
