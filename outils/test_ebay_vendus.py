"""Sonde : la page eBay « objets vendus » est-elle lisible depuis GitHub ? (gratuit)"""
import re, urllib.parse, urllib.request
q = "nintendo switch 2"
u = "https://www.ebay.fr/sch/i.html?_nkw=" + urllib.parse.quote(q) + "&LH_Sold=1&LH_Complete=1&_sop=13&_ipg=120"
h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept-Language": "fr-FR,fr;q=0.9"}
try:
    with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=30) as r:
        t = r.read().decode("utf-8", "replace"); print("HTTP", r.status, len(t))
except Exception as e:
    print("HTTP erreur", e); t = ""
print("Vendu le:", len(re.findall(r"Vendu le", t)), "| s-card:", t.count("s-card"), "| s-item:", t.count("s-item"))
for m in list(re.finditer(r"Vendu le[^<]{0,40}", t))[:5]:
    print(" ", m.group(0))
i = t.find("Vendu le")
print(re.sub(r"<[^>]+>", " ", t[i:i+3000])[:1500] if i > 0 else t[:1500])
