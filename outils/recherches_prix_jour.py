"""Remplit d'un coup les prix des plus recherchés et de la hype (jetons Keepa déjà payés, 0 €). outil = recherches_prix_jour"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import moisson, recherches_prix
etat = moisson._etat()
print("mis à jour :", recherches_prix.tour(etat, maxi=40, maxi_hype=100))
