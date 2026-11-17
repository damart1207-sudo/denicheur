"""Test réel du marché des écarts vendeurs (denicheur/marche.py) sur les VRAIES affaires du jour (data/ecarts.json).
Pour les NB meilleures : Leboncoin, Vinted, eBay, comparateurs, volume de recherche, bilan de l'expert et de l'acheteur (1 appel d'IA par affaire), puis l'alerte complète sur Telegram.
Coût : eBay et achatmoinscher gratuits ; Apify 0,05 $ réservés par affaire (≈ 0,03 $ réels), plafond « E » ;
volume : cache, sinon un appel DataForSEO Labs (≈ 0,013 $) seulement s'il reste du plafond du jour. Aucun jeton Keepa.
outil = test_ecart_marche"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import apify, bilan, dataforseo, ecart, marche, telegram

NB = int(os.environ.get("NB", "2"))
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
    f["bilan"] = bilan.rediger(f)
    print("--- fiche donnée à l'IA ---\n" + bilan.fiche_texte(f) + "\n--- bilan ---\n" + json.dumps(f["bilan"], ensure_ascii=False))
    print(json.dumps({k: f.get(k) for k in ("titre", "nom_court", "ean", "premier", "second", "volume", "volume_mot", "marche")}, ensure_ascii=False, indent=1))
    texte = f"🔁 Affaire du jour (prix relevé à {f['vu'][11:]} UTC), avec le bilan de l'expert et de l'acheteur\n" + ecart.message(f)
    print(texte)
    print("Telegram :", telegram.envoyer(texte))
# Vinted : le robot donne-t-il une date de publication ? (schéma gratuit + champs d'une annonce de l'étude ci-dessus)
import urllib.request
try:
    req = urllib.request.Request("https://api.apify.com/v2/acts/" + apify.ROBOTS["vinted"][0] + "/builds/default",
                                 headers={"Authorization": "Bearer " + os.environ["APIFY_TOKEN"].strip()})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("data") or {}
    sch = (d.get("actorDefinition") or {}).get("input") or d.get("inputSchema")
    sch = json.loads(sch) if isinstance(sch, str) else sch
    for k, v in ((sch or {}).get("properties") or {}).items():
        print("  vinted champ", k, "|", v.get("type"), "|", str(v.get("default"))[:40], "|", str(v.get("enum"))[:150], "|", (v.get("description") or v.get("title") or "")[:140].replace("\n", " "))
except Exception as e:
    print("schéma vinted :", type(e).__name__, e)
print(f"réserve volume prise aujourd'hui : {marche._reserve_du_jour()}")
print(f"DataForSEO dépensé après : {dataforseo._budget()['depense_usd']} $")
