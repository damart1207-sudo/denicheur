"""Demande d'un produit collé par David : se vend-il (Keepa, 1 à 2 jetons) et est-il recherché (DataForSEO, un appel
à 0,09 $ seulement si le plafond du jour le permet, sinon rien n'est dépensé) ?
config/demande_produit.json : {"ean": "...", "mots": ["..."]}. outil = demande_produit -> data/demande_produit.json"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import keepa, dataforseo

cfg = json.load(open("config/demande_produit.json"))
res = {"ean": cfg["ean"], "maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "amazon": [], "volumes": {}, "notes": []}
try:
    d = keepa._lire({"key": keepa.cle(), "domain": 4, "code": cfg["ean"], "stats": 90, "history": 0})
    for p in d.get("products") or []:
        if not isinstance(p, dict) or cfg["ean"].zfill(14) not in [str(c).zfill(14) for c in (p.get("eanList") or [])]:
            continue
        f = keepa._parser(p, 4, "FR", d.get("tokensLeft"))
        f["achetes_mois_amazon"] = p.get("monthlySold")
        f["nb_avis"] = ((p.get("stats") or {}).get("current") or [None] * 18)[17]
        res["amazon"].append(f)
except Exception as e:
    res["notes"].append(f"keepa: {type(e).__name__}: {str(e)[:100]}")
try:
    if dataforseo.disponible(dataforseo.COUT["volumes"]):
        res["volumes"] = dataforseo.volumes(cfg["mots"])
    else:
        res["notes"].append("volume : plafond DataForSEO du jour déjà atteint, aucun appel fait")
except Exception as e:
    res["notes"].append(f"dataforseo: {type(e).__name__}: {str(e)[:100]}")
json.dump(res, open("data/demande_produit.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:1500])
