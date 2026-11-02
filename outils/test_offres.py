"""Test : lire TOUTES les offres (boutique + prix) d'un produit sur achatmoinscher, pour comparer
le moins cher au prix habituel. Sauve un échantillon HTML pour mise au point du lecteur."""
import json, os, re, sys
sys.path.insert(0, os.getcwd())
from denicheur import comparateurs as c

os.makedirs("data/echantillons", exist_ok=True)
res = {}
for nom in ["iPhone 17 256 Go", "PlayStation 5 Slim", "AirPods Pro 3"]:
    try:
        offres = [o for o in c.achatmoinscher(nom) if c.correspond(o["titre"], nom)]
        res[nom] = {"recherche": offres[:5]}
        if offres:
            h = c._lire(offres[0]["lien"])
            if nom.startswith("iPhone"):
                open("data/echantillons/amc_produit.html", "w", encoding="utf-8").write(h[:400000])
            prix = re.findall(r'(\d[\d\s.]*,\d{2})\s*(?:&nbsp;)?€', h)
            res[nom]["page"] = {"taille": len(h), "nb_prix_trouves": len(prix), "prix": prix[:30],
                                "ld_json": len(re.findall(r"application/ld\+json", h))}
    except Exception as e:
        res[nom] = {"erreur": str(e)[:200]}
json.dump(res, open("data/echantillons/test_offres.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:2000])
