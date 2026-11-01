"""Teste les flux de bons plans asiatiques (gratuit)."""
import json
import re
import urllib.request

URLS = {
    "smzdm_cn": "https://feed.smzdm.com",
    "smzdm_cn_2": "https://www.smzdm.com/feed",
    "smzdm_haitao": "https://haitao.smzdm.com/feed",
    "ppomppu_kr": "https://www.ppomppu.co.kr/rss.php?id=ppomppu",
    "ppomppu_kr_etranger": "https://www.ppomppu.co.kr/rss.php?id=ppomppu4",
    "quasarzone_kr": "https://quasarzone.com/bbs/qb_saleinfo/rss",
    "ozbargain_au": "https://www.ozbargain.com.au/deals/feed",
    "desidime_in": "https://www.desidime.com/new.atom",
    "kakaku_jp_news": "https://news.kakaku.com/prdnews/rss.asp",
    "slickdeals_us": "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
    "redflagdeals_ca": "https://forums.redflagdeals.com/feed/forum/9",
    "pepper_com_global": "https://www.pepper.com/rss/hot",
}
res = {}
for nom, u in URLS.items():
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; Denicheur/1.0)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            h = r.read().decode("utf-8", errors="replace")
        titres = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", h, re.S)[1:6]
        res[nom] = {"ok": True, "items": h.count("<item") + h.count("<entry"), "exemples": [t.strip()[:90] for t in titres]}
    except Exception as e:
        res[nom] = {"ok": False, "erreur": f"{type(e).__name__}: {str(e)[:100]}"}
    print(nom, res[nom])
with open("data/test_asie.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
