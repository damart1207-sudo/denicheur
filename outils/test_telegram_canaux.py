"""Sonde (gratuit) : quelles chaînes Telegram publiques de bons plans existent et donnent des prix ?
-> data/echantillons/test_telegram_canaux.json     Lancement : outil = test_telegram_canaux"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import telegram_canaux  # noqa: E402
CANDIDATS = ["promorat", "dealabs", "dealabsfr", "erreurdeprix", "erreursdeprix", "erreurs_de_prix", "bonsplans", "bonplans",
             "bons_plans", "bonplanfr", "bonsplansfr", "dealsfr", "amazonbonsplans", "bonsplansamazon", "promosamazon", "codepromo",
             "bonnesaffaires", "lesbonsplans", "bonsplansdujour", "pricedrop", "glitchdeals", "hotdealsfr", "radins", "jeuxvideobonsplans"]
res = {}
for c in CANDIDATS:
    ann, err = telegram_canaux.lire({"chaine": c})
    res[c] = {"erreur": err, "nb": len(ann), "exemples": [(a["titre"][:80], a["prix"], a["date"]) for a in ann[-3:]]}
    print(c, err or "", len(ann), res[c]["exemples"][-1:] if ann else "")
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_telegram_canaux.json", "w"), ensure_ascii=False, indent=1)
