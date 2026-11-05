"""Test réel (gratuit) du contrôle de prix sur fiche produit : Makita LS1019L (vrai 751,75 €), Carrera (64,90 €), Makita MLT100N.
Lancement : outil = test_verif_prix"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import verif_prix  # noqa: E402
for lien, prix in (("https://www.manomano.fr/p/makita-ls1019l-scie-a-onglet-radiale-avec-laser-1510w-260-x-30mm-24014748", 510.75),
                   ("https://www.manomano.fr/p/seche-serviette-lcd-plusieures-puissances-disponibles-4260069", 64.90),
                   ("https://www.manomano.fr/p/scie-circulaire-sur-table-260mm-1500w-makita-mlt100n-40047941?product_id=26758555", 578.0)):
    print(prix, "->", verif_prix.controler({"lien": lien, "prix": prix}), lien[:70])
