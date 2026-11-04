"""Test du bingo (≈ 0,09 $ DataForSEO + 20 jetons Keepa) : réponse BRUTE des volumes Google sur 40 mots-clés réels
du bingo, et recherche Keepa par nom (ASIN/EAN) sur 2 produits réels du dernier passage.
-> data/echantillons/test_bingo.json      Lancement : workflow « Dénicheur », outil = test_bingo"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import bingo, dataforseo, moisson  # noqa: E402

res = {}
cands = bingo.candidats()
mots = list(cands)[:40]
res["mots"] = mots
try:
    taches = dataforseo._poster("keywords_data/google_ads/search_volume/live",
                                [{"keywords": mots, "location_code": 2250, "language_code": "fr"}], 0.09)
    res["brut"] = taches[:1]
    res["resultat"] = [{k: it.get(k) for k in ("keyword", "search_volume", "competition", "cpc")} for t in taches for it in (t.get("result") or []) if isinstance(it, dict)][:40]
except Exception as e:
    res["erreur_volumes"] = f"{type(e).__name__}: {str(e)[:400]}"
# recherche Keepa par nom (10 jetons par recherche) sur 2 produits réels du dernier passage
try:
    p = json.load(open("data/dernier_passage.json", encoding="utf-8"))
    noms = [c.get("nom_produit") for c in p.get("candidats", []) if c.get("nom_produit")][:2]
    res["keepa_recherche"] = {}
    for n in noms:
        d = moisson._appel("search", {"domain": 4, "type": "product", "term": n, "stats": 90, "history": 0})
        res["keepa_recherche"][n] = {"cles": list(d.keys()), "produits": [{"asin": x.get("asin"), "titre": (x.get("title") or "")[:80], "ean": (x.get("eanList") or [None])[0],
                                                                           "neuf": ((x.get("stats") or {}).get("current") or [None, None])[1]} for x in (d.get("products") or [])[:5]]}
except Exception as e:
    res["erreur_keepa"] = f"{type(e).__name__}: {str(e)[:300]}"
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_bingo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "brut"}, ensure_ascii=False)[:4000])
