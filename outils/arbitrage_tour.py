"""Un tour d'arbitrage Europe à la main (50 produits x 4 pays = 200 jetons Keepa, 0 €). outil = arbitrage_tour"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import arbitrage
print("écarts trouvés :", arbitrage.tour(par_tour=50))
