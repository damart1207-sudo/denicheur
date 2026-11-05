"""Sonde 2 (gratuit) : prospectus Bonial — page d'une enseigne, liens vers les prospectus, images des pages.
-> data/echantillons/test_prospectus.json     Lancement : outil = test_prospectus"""
import json, os, re, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR,fr;q=0.9"}
def get(u, binaire=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=40) as r:
            b = r.read()
            return r.status, (b if binaire else b.decode("utf-8", "ignore")), r.headers.get("Content-Type")
    except Exception as e:
        return str(e)[:100], b"" if binaire else "", None
res = {}
st, h, _ = get("https://www.bonial.fr/Enseignes/Lidl")
uuids = list(dict.fromkeys(re.findall(r"content-media\.bonial\.biz/([0-9a-f-]{36})/", h)))
liens = list(dict.fromkeys(u for u in re.findall(r'href="([^"]+)"', h) if re.search(r"(?i)prospectus|catalogue|brochure|/Lidl/", u)))
res["enseigne"] = {"statut": st, "taille": len(h), "uuids": uuids[:5], "liens": liens[:15],
                   "json_pages": [m[:300] for m in re.findall(r'"(?:pages|pageCount|totalPages|brochureId|contentId)"\s*:[^,\]]{0,300}', h)[:15]]}
essais = {}
if uuids:
    u = uuids[0]
    for motif in ("preview.jpg", "page_1.jpg", "page-1.jpg", "pages/1.jpg", "1.jpg", "page_2.jpg", "pages/page_1.jpg", "1/page.jpg"):
        s2, b, ct = get(f"https://content-media.bonial.biz/{u}/{motif}", binaire=True)
        essais[motif] = [s2, len(b), ct]
res["essais_images"] = essais
for l in liens[:2]:
    url = l if l.startswith("http") else "https://www.bonial.fr" + l
    s3, h3, _ = get(url)
    res.setdefault("prospectus", []).append({"url": url, "statut": s3, "taille": len(h3),
        "images": list(dict.fromkeys(re.findall(r"https://content-media\.bonial\.biz/[^\"'\s)]+", h3)))[:30],
        "json": [m[:300] for m in re.findall(r'"(?:pages|imageUrl|url)"\s*:\s*"[^"]{0,200}"', h3)[:15]]})
print(json.dumps(res, ensure_ascii=False, indent=1)[:4000])
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_prospectus.json", "w"), ensure_ascii=False, indent=1)
