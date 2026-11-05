"""Sonde 3 : structure exacte du tableau "pages" des prospectus Bonial (page enseigne Lidl) et test des URL d'images.
Lancement : outil = test_prospectus"""
import re, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR"}
h = urllib.request.urlopen(urllib.request.Request("https://www.bonial.fr/Enseignes/Lidl", headers=H), timeout=40).read().decode("utf-8", "ignore")
i = h.find('"pages":[')
print("EXTRAIT:", h[i:i + 1500].replace("\\u002F", "/"))
urls = list(dict.fromkeys(re.findall(r'https?:(?:\\u002F|/){2}content-media\.bonial\.biz(?:\\u002F|/)[^"\\]+', h)))
print("NB URLS:", len(urls))
for u in urls[:12]:
    u = u.replace("\\u002F", "/")
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={**H, "Referer": "https://www.bonial.fr/"}), timeout=30)
        print("OK", r.status, len(r.read()), u)
    except Exception as e:
        print("KO", str(e)[:40], u)
