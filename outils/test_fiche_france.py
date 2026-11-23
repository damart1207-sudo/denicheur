"""Test RÉEL du correctif « vraie fiche française » (23/11/2026), sans aucun envoi Telegram et sans rien écrire dans data/.
Reprend les 10 produits du dernier top USA enregistré + 8 produits « absents » du fichier hype, et affiche ce que le
robot dirait maintenant. Coût : ≈ 200 jetons Keepa au plus (compris dans l'abonnement), 0 €.   Lancement : outil = test_fiche_france"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import classements, moisson  # noqa: E402
from denicheur.telegram import _e, _eur  # noqa: E402

debut = moisson.jetons_restants()
print("jetons Keepa au départ :", debut)
if debut < 150:
    sys.exit("pas assez de jetons pour tester sans gêner la veille : relancer plus tard")

dernier = sorted(glob.glob("data/classements/US/*.json"))[-1]
top = json.load(open(dernier, encoding="utf-8"))["top"]
print("\n===== TOP USA de", os.path.basename(dernier), "=====")
labas = moisson.fiches([x["asin"] for x in top], "US")
vues = moisson.fiche_france(labas, {x["asin"]: x["prix_eur"] for x in top}, par_nom=len(top))
for x in top:
    avant = x.get("france")
    print(f"\n{x['asin']} {x['titre'][:60]} · là-bas {x['prix_eur']} €")
    print("  AVANT :", "absent d'Amazon France" if not avant else f"en France : {avant.get('prix')} €, {avant.get('vendeurs')} vendeurs")
    v = vues.get(x["asin"])
    print("  APRÈS :", classements.ligne_france(v, _eur, _e).replace("\n", " "),
          "| trouvé par :", (v or {}).get("trouve_par"), "| titre FR :", ((v or {}).get("titre") or "")[:60],
          "| ressemblance :", (v or {}).get("ressemblance"))

if (moisson._jetons["restants"] or 0) < 60:
    print("\njetons dépensés par ce test :", moisson._jetons["depenses"], "| restants :", moisson._jetons["restants"])
    sys.exit(0)
print("\n===== 8 produits « absents » du fichier hype (code-barres seulement) =====")
hype = [h for h in json.load(open("data/hype_etranger.json", encoding="utf-8")).get("produits", [])
        if h.get("pays") == "US" and h.get("en_france") == "absent"][-8:]
labas = moisson.fiches([h["asin"] for h in hype], "US")
vues = moisson.fiche_france(labas, {r["asin"]: round((r.get("neuf") or 0) * 0.90, 2) or None for r in labas})
bilan = {}
for r in labas:
    v = vues.get(r["asin"]) or {}
    bilan[v.get("etat")] = bilan.get(v.get("etat"), 0) + 1
    print(f"{r['asin']} {r['t'][:50]} -> {v.get('etat')} ({v.get('trouve_par')}) {v.get('prix')} € rang {v.get('rang')} {v.get('asin')}")
print("bilan hype :", bilan)
print("\njetons dépensés par ce test :", moisson._jetons["depenses"], "| restants :", moisson._jetons["restants"])
