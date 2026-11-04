"""Test GRATUIT du lecteur de pages (denicheur/lecteur.py) depuis GitHub : lit la page du bon plan et celle du marchand
pour les 8 alertes les plus récentes de chaque type de source (Pepper, article, Amazon…). Aucune IA, aucun robot payant.
-> data/test_lecteur.json      outil = test_lecteur"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import lecteur  # noqa: E402

alertes = json.load(open("data/alertes.json", encoding="utf-8"))
choisies, vus = [], set()
for x in reversed(alertes):
    dom = lecteur._domaine(x.get("lien") or "")
    if not dom:
        continue
    cle = dom.split(".")[-2] if "." in dom else dom
    if sum(1 for c in choisies if c[0] == cle) >= 2 or len(choisies) >= 10:
        continue
    choisies.append((cle, x))
res = {}
for cle, x in choisies:
    t0 = time.time()
    p = lecteur.lire_offre(x)
    p["duree_s"] = round(time.time() - t0, 1)
    res[x["id"]] = {"titre": x["titre"][:80], "prix_alerte": x.get("prix"), "pays": x.get("pays"), "lien": x.get("lien"), "page_offre": p}
    print(f"{x['id']} {cle:14s} {p['duree_s']:5.1f}s | {p.get('resume')}", flush=True)
os.makedirs("data", exist_ok=True)
json.dump(res, open("data/test_lecteur.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
