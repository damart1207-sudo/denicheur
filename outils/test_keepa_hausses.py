"""Test Keepa (≈ 12 jetons) : Product Finder « produits qui montent » = classement actuel bien meilleur que sa moyenne 30 j.
Vérifie les noms de champs deltaPercent30_SALES / avg30_SALES. outil = test_keepa_hausses"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import moisson
res = {}
for nom, sel in {"deltaPercent30": {"deltaPercent30_SALES_lte": -50, "current_SALES_lte": 20000, "current_NEW_gte": 1500, "current_NEW_lte": 60000, "productType": 0, "perPage": 50, "page": 0, "sort": [["deltaPercent30_SALES", "asc"]]},
                 "delta90": {"deltaPercent90_SALES_lte": -60, "current_SALES_lte": 20000, "current_NEW_gte": 1500, "productType": 0, "perPage": 50, "page": 0}}.items():
    try:
        d = moisson._appel("query", {"domain": 4, "selection": json.dumps(sel)})
        res[nom] = {"nb": len(d.get("asinList") or []), "total": d.get("totalResults"), "erreur": d.get("error"), "asins": (d.get("asinList") or [])[:5]}
    except Exception as e:
        res[nom] = {"erreur": f"{type(e).__name__}: {str(e)[:300]}"}
    print(nom, res[nom])
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_keepa_hausses.json", "w"), indent=1)
