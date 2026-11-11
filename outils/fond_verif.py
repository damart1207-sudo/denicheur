"""Produits de fond : (1) qui vend sur la fiche Amazon (Keepa, ≈ 9 jetons par produit, 0 €) ;
(2) volumes de recherche Google France mois par mois (DataForSEO, UN seul appel payant : 0,09 $).
Garde-fous : un seul appel DataForSEO facturé au plus (le plafond du jour bloque tout second appel), 10 min au plus.
outil = fond_verif   ->   data/fond_verif.json"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import keepa, dataforseo as dfs

ASINS = {"B01G1Z0RF0": "CompuCleaner Xpert", "B076H44LDP": "Pyrex lot 3 plats", "B0CH8LJL3Y": "COROS capteur cardiaque",
         "B0D2HKCMBP": "Shokz OpenRun Pro 2", "B08B3VCGCH": "Veddelholzer articulations chien", "B09LHF7QVT": "Victiv trépied",
         "B07Q4JVFNH": "Dilamababy coussin grossesse", "B08X7D5R67": "SOULWIT coussinets Bose 700"}
MOTS = ["compucleaner", "compucleaner xpert", "souffleur électrique pc", "souffleur air comprimé électrique", "dépoussiéreur électrique",
        "pyrex", "plat à four pyrex", "plat pyrex", "plat à four en verre", "coros", "ceinture cardio coros", "ceinture cardio",
        "capteur fréquence cardiaque", "shokz", "shokz openrun pro 2", "casque conduction osseuse", "complément articulation chien",
        "comprimés articulations chien", "arthrose chien", "veddelholzer", "trépied smartphone", "trépied téléphone", "trépied appareil photo",
        "coussin de grossesse", "coussin allaitement", "coussin de maternité", "coussinets bose 700", "coussinets casque bose",
        "mousse casque bose", "petsafe scoopfree", "chatière à puce"]
res = {"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "vendeurs": {}, "volumes": {}, "notes": []}
SORTIE = "data/fond_verif.json"


def ecrire():
    json.dump(res, open(SORTIE, "w"), ensure_ascii=False, indent=1)


# 1) volumes Google, avec l'historique le plus long accepté ; si la période est refusée (tâche en erreur = non facturée), 12 mois par défaut
def appel(extra):
    return dfs._poster("keywords_data/google_ads/search_volume/live",
                       [{"keywords": MOTS, "location_code": 2250, "language_code": "fr", **extra}], dfs.COUT["volumes"])

for extra in ({"date_from": "2022-12-01"}, {}):
    try:
        if not dfs.disponible(dfs.COUT["volumes"]):
            res["notes"].append("DataForSEO : plafond du jour atteint, appel non fait")
            break
        taches = appel(extra)
        t = (taches or [{}])[0]
        res["notes"].append(f"DataForSEO {extra or '12 mois'} : {t.get('status_code')} {t.get('status_message')} coût {t.get('cost')}")
        if t.get("status_code") == 20000 and t.get("result"):
            for it in t["result"]:
                res["volumes"][it.get("keyword")] = {"moyen": it.get("search_volume"), "concurrence": it.get("competition"), "cpc": it.get("cpc"),
                    "mois": {f'{h.get("year")}-{h.get("month"):02d}': h.get("search_volume") for h in (it.get("monthly_searches") or [])}}
            break
    except Exception as e:
        res["notes"].append(f"DataForSEO {extra or '12 mois'} : {type(e).__name__} {str(e)[:200]}")
ecrire()

# 2) vendeurs présents sur chaque fiche
for asin, nom in ASINS.items():
    try:
        res["vendeurs"][asin] = {"produit": nom, "offres": keepa.vendeurs(asin, "FR", 6)}
    except Exception as e:
        res["vendeurs"][asin] = {"produit": nom, "erreur": f"{type(e).__name__}: {str(e)[:150]}"}
    ecrire()
print(json.dumps(res["notes"], ensure_ascii=False), len(res["volumes"]), "mots,", len(res["vendeurs"]), "fiches")
