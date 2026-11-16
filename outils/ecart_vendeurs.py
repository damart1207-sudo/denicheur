"""Écart entre le vendeur le moins cher et le SECOND sur Amazon.fr (idée de David, 16/11/2026, cas de l'écran iiyama :
1er vendeur 92,19 €, 2e 142,59 €). Candidats = baisses neuves du radar du jour (data/radar_amazon.json, déjà payées).
Pour chacun : les offres neuves en cours (Keepa, 6 jetons par page de 10 offres, 2 pages) triées prix + port.
Garde-fous : 25 produits au plus, jamais sous 160 jetons de réserve, 15 minutes au plus, 0 € (abonnement Keepa).
outil = ecart_vendeurs -> data/ecart_vendeurs.json"""
import json, os, sys, time
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import keepa

MAXI, RESERVE, DUREE_MAX = 25, 160, 900
jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
radar = [a for a in json.load(open("data/radar_amazon.json")).get("affaires", [])
         if a.get("type") == "neuf" and (a.get("vu") or "")[:10] == jour and (a.get("prix") or 0) >= 40
         and a.get("moyenne_90j") and (a.get("rang") or 10**9) <= 50000 and a["moyenne_90j"] <= a["prix"] * 3]
radar.sort(key=lambda a: -(a["moyenne_90j"] - a["prix"]))
res = {"maj": None, "regle": "écart = 2e offre neuve − 1re offre neuve (prix + port), offres en cours sur Amazon.fr",
       "examines": 0, "produits": [], "notes": []}
debut, jetons = time.monotonic(), None
for a in radar[:MAXI]:
    while jetons is not None and jetons < RESERVE and time.monotonic() - debut < DUREE_MAX:
        time.sleep(60)
        jetons += 20
    if time.monotonic() - debut >= DUREE_MAX:
        res["notes"].append("arrêt : 15 minutes atteintes")
        break
    try:
        d = keepa._lire({"key": keepa.cle(), "domain": 4, "asin": a["asin"], "offers": 20, "history": 0, "stats": 0})
    except Exception as e:
        res["notes"].append(f'{a["asin"]}: {type(e).__name__}: {str(e)[:80]}')
        if "429" in str(e):
            jetons = 0
        continue
    jetons = d.get("tokensLeft")
    p = (d.get("products") or [None])[0]
    if not p:
        continue
    offres = p.get("offers") or []
    vivantes = p.get("liveOffersOrder")
    if isinstance(vivantes, list):
        offres = [offres[i] for i in vivantes if isinstance(i, int) and i < len(offres)]
    lignes = []
    for o in offres:
        h = o.get("offerCSV") or []
        if not isinstance(o, dict) or o.get("condition") != 1 or len(h) < 3 or not isinstance(h[-2], (int, float)) or h[-2] <= 0:
            continue
        port = h[-1] if isinstance(h[-1], (int, float)) and h[-1] > 0 else 0
        lignes.append({"total": round((h[-2] + port) / 100, 2), "amazon": bool(o.get("isAmazon")), "fba": bool(o.get("isFBA")), "vendeur": o.get("sellerId")})
    lignes.sort(key=lambda x: x["total"])
    res["examines"] += 1
    f = {"asin": a["asin"], "titre": a.get("titre"), "lien": a.get("lien"), "prix_radar": a["prix"], "moyenne_90j": a["moyenne_90j"],
         "rang": a.get("rang"), "nb_offres_neuves": len(lignes), "offres": lignes[:4]}
    if len(lignes) >= 2:
        f["premier"], f["second"] = lignes[0]["total"], lignes[1]["total"]
        f["ecart"] = round(lignes[1]["total"] - lignes[0]["total"], 2)
        f["ecart_pct"] = round(f["ecart"] / lignes[1]["total"] * 100)
    res["produits"].append(f)
    res["maj"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    res["jetons_fin"] = jetons
    json.dump(res, open("data/ecart_vendeurs.json", "w"), ensure_ascii=False, indent=1)
res["produits"].sort(key=lambda f: -(f.get("ecart") or -1))
json.dump(res, open("data/ecart_vendeurs.json", "w"), ensure_ascii=False, indent=1)
print(f'{res["examines"]} produits examinés, {sum(1 for f in res["produits"] if (f.get("ecart") or 0) >= 50)} avec ≥ 50 € entre le 1er et le 2e vendeur')
