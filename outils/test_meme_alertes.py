"""Rejoue le contrôle « même produit » sur les 80 dernières alertes réelles (data/alertes.json), sans rien envoyer.
Affiche, pour chacune : verdict, raison, titre de l'annonce et titre de la référence France.  Lancement : outil = test_meme_alertes"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import meme_produit  # noqa: E402

a = [x for x in json.load(open("data/alertes.json", encoding="utf-8")) if x.get("prix_plancher")][-80:]
n = {True: 0, False: 0, None: 0}
for x in a:
    r = meme_produit.controler_alerte(x)
    n[r["meme"]] += 1
    print({True: "MÊME   ", False: "ÉCARTÉ ", None: "?      "}[r["meme"]], f"{x.get('prix')} € vs {x['prix_plancher'].get('prix_min')} € |",
          str(x.get("titre"))[:70], "<>", str(r.get("reference"))[:70], "—", r.get("raison"))
print("BILAN même produit", n[True], "| écartées", n[False], "| non confirmées", n[None], "sur", len(a))
