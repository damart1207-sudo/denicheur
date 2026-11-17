"""Test réel du marché des écarts vendeurs (denicheur/marche.py) sur les VRAIES affaires du jour (data/ecarts.json).
Pour les NB meilleures : Leboncoin, Vinted, eBay, comparateurs, volume de recherche, puis l'alerte complète sur Telegram.
Coût : eBay et achatmoinscher gratuits ; Apify 0,05 $ réservés par affaire (≈ 0,03 $ réels), plafond « E » ;
volume : cache, sinon un appel DataForSEO Labs (≈ 0,013 $) seulement s'il reste du plafond du jour. Aucun jeton Keepa.
outil = test_ecart_marche"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import apify, dataforseo, ecart, marche, telegram

NB = int(os.environ.get("NB", "3"))
base = ecart._lire(ecart.F_ECARTS, {})
lot = [dict(f) for f in base.get("affaires", []) if f.get("retenu")][:NB]
print(f"{len(lot)} affaires du {base.get('jour')} ; Apify disponible : {apify.disponible()} ; DataForSEO dépensé : {dataforseo._budget()['depense_usd']} $")
t0 = time.time()
marche.etudier(lot)
print(f"étude du marché : {time.time() - t0:.0f} s ; Apify E dépensé (journal) : {apify.depense_du_jour('E'):.3f} $")
vol = marche.volumes([f["nom_court"] for f in lot])
for f in lot:
    v = vol.get(f["nom_court"])
    f["volume"], f["volume_mot"] = (v["v"], v["mot"]) if v else (None, None)
    print(json.dumps({k: f.get(k) for k in ("titre", "nom_court", "ean", "premier", "second", "volume", "volume_mot", "marche")}, ensure_ascii=False, indent=1))
    texte = f"🔁 Affaire du jour (prix relevé à {f['vu'][11:]} UTC), version vérifiée : Leboncoin, Vinted, eBay, comparateurs\n" + ecart.message(f)
    print(texte)
    print("Telegram :", telegram.envoyer(texte))
print(f"DataForSEO dépensé après : {dataforseo._budget()['depense_usd']} $")
