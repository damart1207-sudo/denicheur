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
journal = []
for r in labas:
    print("codes-barres", r["asin"], r.get("codes"), "| marque", r.get("marque"))
vues = moisson.fiche_france(labas, {x["asin"]: x["prix_eur"] for x in top}, par_nom=len(top), journal=journal)
print("\n".join(journal))
from denicheur import sante  # noqa: E402
print("erreurs notées :", [e for e in sante._lire()["evenements"] if e["etape"] == "fiche france"][-10:])
for x in top:
    avant = x.get("france")
    print(f"\n{x['asin']} {x['titre'][:60]} · là-bas {x['prix_eur']} €")
    print("  AVANT :", "absent d'Amazon France" if not avant else f"en France : {avant.get('prix')} €, {avant.get('vendeurs')} vendeurs")
    v = vues.get(x["asin"])
    print("  APRÈS :", classements.ligne_france(v, _eur, _e).replace("\n", " "),
          "| trouvé par :", (v or {}).get("trouve_par"), "| titre FR :", ((v or {}).get("titre") or "")[:60],
          "| ressemblance :", (v or {}).get("ressemblance"))

print("\njetons dépensés par ce test :", moisson._jetons["depenses"], "| restants :", moisson._jetons["restants"])
