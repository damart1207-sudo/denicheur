"""Test du moissonneur Keepa (gratuit, ≈ 60 jetons) : garde une réponse BRUTE de chaque appel pour vérifier
les noms de champs (deal, bestsellers, query). -> data/echantillons/keepa_brut.json
Lancement : workflow « Dénicheur » avec outil = test_moisson"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import moisson  # noqa: E402

res = {}
try:
    d = moisson._appel("deal", {"domain": 4}, corps={"page": 0, "domainId": 4, "priceTypes": [1], "dateRange": 0, "isFilterEnabled": True,
                                                   "deltaPercentRange": [20, 95], "currentRange": [1200, 45000], "salesRankRange": [1, 60000],
                                                   "singleVariation": True, "filterErotic": True, "hasReviews": True})
    dr = (d.get("deals") or {}).get("dr") or []
    res["deal"] = {"cles_reponse": list(d.keys()), "cles_deals": list((d.get("deals") or {}).keys()), "nb": len(dr),
                   "exemples": [{k: v for k, v in x.items() if k != "image"} for x in dr[:3]]}
except Exception as e:
    res["deal"] = {"erreur": f"{type(e).__name__}: {str(e)[:300]}"}
for pays, cat in (("US", "Electronics"), ("JP", "Electronics"), ("US", "16225007011")):
    try:
        d = moisson._appel("bestsellers", {"domain": moisson.DOMAINES[pays], "category": cat, "range": 30})
        res[f"bestsellers {pays} {cat}"] = {"cles": list(d.keys()), "bestSellersList": {k: (v[:5] if isinstance(v, list) else v) for k, v in (d.get("bestSellersList") or {}).items()},
                                            "erreur": d.get("error")}
    except Exception as e:
        res[f"bestsellers {pays} {cat}"] = {"erreur": f"{type(e).__name__}: {str(e)[:300]}"}
try:
    d = moisson._appel("category", {"domain": 1, "category": 0, "parents": 0})
    res["categories_US"] = {k: v.get("name") for k, v in (d.get("categories") or {}).items()}
    d = moisson._appel("category", {"domain": 5, "category": 0, "parents": 0})
    res["categories_JP"] = {k: v.get("name") for k, v in (d.get("categories") or {}).items()}
except Exception as e:
    res["categories"] = {"erreur": f"{type(e).__name__}: {str(e)[:300]}"}
res["jetons_restants"] = moisson._jetons["restants"]
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/keepa_brut.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:6000])
