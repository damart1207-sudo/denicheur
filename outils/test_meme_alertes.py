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

# cas témoins connus (pièges réels vus le 05/11)
TEMOINS = [("ASUS ROG Strix X870-I Gaming WiFi, AMD Mini-ITX motherboard", "ASUS ROG Strix X870-F Gaming WiFi – Carte mère Gaming AMD", False),
           ("Lot de 2 roues gonflables 260 x 85 mm pour diable", "Lot de 8 roues pleines 260 x 85 mm", False),
           ("Oral-B iO2 Night Black avec étui", "Oral-B iO2 Marine Blue", True),
           ("Sony WH-1000XM5 casque", "Sony WH-1000XM6 casque", False),
           ("iPhone 16 128 Go", "iPhone 16 Pro 128 Go", False)]
ok = 0
for a_, b_, attendu in TEMOINS:
    r = meme_produit.verifier(a_, b_)
    ok += r["meme"] is attendu
    print("TÉMOIN", "OK " if r["meme"] is attendu else "RATÉ", a_[:40], "<>", b_[:40], "—", r["raison"])
print(f"TÉMOINS {ok}/{len(TEMOINS)}")
