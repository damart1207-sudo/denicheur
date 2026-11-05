"""Sonde (gratuit) : depuis GitHub, peut-on lire les prospectus Tiendeo / Bonial et trouver les images de leurs pages ?
-> data/echantillons/test_prospectus.json     Lancement : outil = test_prospectus"""
import json, os, re, sys, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR,fr;q=0.9"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=40) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return str(e)[:120], ""
res = {}
for nom, accueil, motif in (("tiendeo", "https://www.tiendeo.fr/", r'href="(/Catalogues/\d+)"'),
                            ("bonial", "https://www.bonial.fr/", r'href="(https://www\.bonial\.fr/[^"]+/[^"]*(?:catalogue|prospectus|Prospectus)[^"]*)"')):
    st, h = get(accueil)
    liens = list(dict.fromkeys(re.findall(motif, h)))[:3]
    r = {"accueil": st, "taille": len(h), "liens": liens, "catalogues": []}
    for l in liens[:2]:
        u = l if l.startswith("http") else accueil.rstrip("/") + l
        st2, h2 = get(u)
        imgs = list(dict.fromkeys(re.findall(r'https?://[^"\'\s>]+\.(?:jpg|jpeg|webp|png)[^"\'\s>]*', h2)))
        r["catalogues"].append({"url": u, "statut": st2, "taille": len(h2), "nb_images": len(imgs), "images": imgs[:25],
                                "json": [m[:200] for m in re.findall(r'"(?:pages?|imageUrl|image_url|pageUrl)"\s*:\s*[^,]{0,200}', h2)[:10]]})
    res[nom] = r
    print(nom, st, len(h), liens, [(c["statut"], c["nb_images"]) for c in r["catalogues"]])
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_prospectus.json", "w"), ensure_ascii=False, indent=1)
