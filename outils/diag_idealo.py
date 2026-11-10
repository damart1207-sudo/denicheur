"""Diagnostic idealo (Apify) : que renvoie le robot pour un code EAN, puis pour le nom ? 4 recherches ≈ 0,04 $.
Lancement : outil = diag_idealo      Résultat : data/diag_idealo.json"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import apify  # noqa: E402

apify.CONTEXTE["denicheur"] = "P"
CAS = [("0027075311732", "Pentax Papilio III 8.5x21"), ("3016667297926", "Moulinex Multisoup Blender Chauffant")]
res = []
for ean, nom in CAS:
    for q, extra in ((ean, {}), (nom, {})):
        items = apify.lancer("idealo", {"searchQuery": q, "country": "FR", "maxItems": 3, "fetchOffers": False, **extra}, maxi=3)
        print("\n###", q, "->", None if items is None else len(items))
        for i in (items or [])[:3]:
            print(json.dumps(i, ensure_ascii=False)[:1500])
        res.append({"requete": q, "ean": ean, "items": items})
json.dump(res, open("data/diag_idealo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
