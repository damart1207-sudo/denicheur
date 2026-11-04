"""Test gratuit : pages Amazon « hausses de ventes » / « plus souhaités » lisibles depuis le cloud ? Google Trends shopping via pytrends ?
-> data/echantillons/tendances/   outil = test_tendances"""
import json, os, re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
URLS = {"amazon_fr_movers": "https://www.amazon.fr/gp/movers-and-shakers/", "amazon_fr_wished": "https://www.amazon.fr/gp/most-wished-for/",
        "amazon_fr_new": "https://www.amazon.fr/gp/new-releases/", "amazon_de_movers": "https://www.amazon.de/gp/movers-and-shakers/",
        "amazon_com_movers": "https://www.amazon.com/gp/movers-and-shakers/", "amazon_fr_movers_hightech": "https://www.amazon.fr/gp/movers-and-shakers/electronics/"}
os.makedirs("data/echantillons/tendances", exist_ok=True)
res = {}
for nom, u in URLS.items():
    try:
        req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
        with urllib.request.urlopen(req, timeout=25) as r:
            h = r.read(1200000).decode("utf-8", "replace")
        open(f"data/echantillons/tendances/{nom}.html", "w", encoding="utf-8").write(h)
        res[nom] = {"ok": True, "taille": len(h), "titres": len(re.findall(r'class="[^"]*p13n-sc-truncate', h)), "asins": len(set(re.findall(r'/dp/([A-Z0-9]{10})', h))), "captcha": "captcha" in h.lower()}
    except Exception as e:
        res[nom] = {"ok": False, "erreur": f"{type(e).__name__}: {str(e)[:100]}"}
    print(nom, res[nom])
try:
    from pytrends.request import TrendReq
    pt = TrendReq(hl="fr-FR", tz=-60)
    ts = pt.trending_searches(pn="france")
    res["trends_daily"] = ts[0].tolist()[:20]
    pt.build_payload(["casque audio", "aspirateur robot", "airpods", "nintendo switch 2", "friteuse sans huile"], geo="FR", timeframe="now 7-d")
    rq = pt.related_queries()
    res["trends_related"] = {k: (v["rising"].head(8).to_dict("records") if v and v.get("rising") is not None else None) for k, v in rq.items()}
except Exception as e:
    res["trends"] = f"{type(e).__name__}: {str(e)[:150]}"
print(json.dumps({k: v for k, v in res.items() if k.startswith("trends")}, ensure_ascii=False)[:1500])
json.dump(res, open("data/echantillons/tendances/resultat.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
