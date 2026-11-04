"""Test réel des classements (≈ 500 jetons Keepa par pays, sans envoi Telegram) : USA et Royaume-Uni.
-> data/echantillons/test_classements.json     Lancement : outil = test_classements"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import classements  # noqa: E402
res = {}
for p in ("UK", "US"):
    try:
        res[p] = classements.amazon(p)
        print(p, len(res[p]))
        print(classements.message(p, "TEST", res[p])[:1500])
    except Exception as e:
        print(p, "ERREUR", type(e).__name__, e)
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_classements.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
