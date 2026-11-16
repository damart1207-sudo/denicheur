"""Test réel de denicheur/ecart.py (écart entre le 1er et le 2e vendeur Amazon, analyse et alerte Telegram).
Trois tours de 8 produits espacés de 4 minutes (les jetons Keepa se rechargent à 20 par minute).
Coût : jetons Keepa de l'abonnement + au plus un appel DataForSEO groupé (0,09 $, plafond du jour respecté).
outil = ecart_vendeurs -> data/ecarts.json"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import ecart, moisson

total = 0
for i in range(3):
    etat = moisson._etat()
    moisson._jetons.update({"restants": None, "depenses": 0})
    n = ecart.tour(etat)
    etat["jetons_jour"] += moisson._jetons["depenses"]
    moisson._ecrire(moisson.F_ETAT, etat)
    total += n
    print(f"tour {i + 1} : {n} affaires retenues, {moisson._jetons['depenses']} jetons, reste {moisson._jetons['restants']}")
    if i < 2:
        time.sleep(240)
print(f"total : {total} affaires")
