"""Analyse d'un produit Amazon collé par David (config/analyse_lien.json : {"asin": "...", "pays": "ES"}).
Keepa seulement, 0 € : historique complet dans 4 pays (1 jeton chacun) + vendeurs dans le pays du lien et en France (≈ 9 jetons chacun).
Garde-fou : une trentaine de jetons au plus, aucun service payant à l'usage. outil = analyse_lien -> data/analyse_lien.json"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import keepa
from outils.fond_historique import par_mois, ts

cfg = json.load(open("config/analyse_lien.json"))
asin, origine = cfg["asin"], cfg.get("pays", "FR")
pays = [origine] + [p for p in ("FR", "DE", "IT", "ES") if p != origine]
res = {"asin": asin, "maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "pays": {}, "vendeurs": {}, "notes": []}
for p in pays:
    try:
        d = keepa._lire({"key": keepa.cle(), "domain": keepa.DOMAINES.get(p, 4), "asin": asin, "stats": 90, "history": 1})
        pr = (d.get("products") or [None])[0]
        if not pr or not pr.get("title"):
            res["pays"][p] = {"absent": True}
            continue
        csv = pr.get("csv") or []
        g = lambda i: csv[i] if len(csv) > i else None
        st = pr.get("stats") or {}
        cur = st.get("current") or []
        c = lambda i: (cur[i] if len(cur) > i and isinstance(cur[i], int) and cur[i] > 0 else None)
        res["pays"][p] = {"titre": pr.get("title"), "marque": pr.get("brand"), "ean": (pr.get("eanList") or [None])[0],
            "categorie": [x.get("name") for x in (pr.get("categoryTree") or [])], "poids_g": pr.get("packageWeight"),
            "suivi_depuis": datetime.fromtimestamp(ts(pr["trackingSince"]), timezone.utc).strftime("%Y-%m") if pr.get("trackingSince") else None,
            "vendus_mois": pr.get("monthlySold"), "prix_neuf": (c(1) or 0) / 100 or None, "prix_amazon": (c(0) or 0) / 100 or None,
            "rang": c(3), "nb_vendeurs_neuf": c(11), "baisses_rang_30j": st.get("salesRankDrops30"), "baisses_rang_90j": st.get("salesRankDrops90"),
            "note": (c(16) or 0) / 10 or None, "nb_avis": c(17),
            "h_rang": par_mois(g(3)), "h_prix_neuf": par_mois(g(1), 100), "h_prix_amazon": par_mois(g(0), 100),
            "h_vendeurs": par_mois(g(11)), "h_vendus_mois": par_mois(pr.get("monthlySoldHistory"))}
        res["notes"].append(f"{p}: jetons {d.get('tokensLeft')}")
    except Exception as e:
        res["pays"][p] = {"erreur": f"{type(e).__name__}: {str(e)[:150]}"}
    json.dump(res, open("data/analyse_lien.json", "w"), ensure_ascii=False, separators=(",", ":"))
for p in dict.fromkeys([origine, "FR"]):
    if not res["pays"].get(p, {}).get("titre"):
        continue
    try:
        res["vendeurs"][p] = keepa.vendeurs(asin, p, 8)
    except Exception as e:
        res["vendeurs"][p] = [{"erreur": str(e)[:150]}]
    json.dump(res, open("data/analyse_lien.json", "w"), ensure_ascii=False, separators=(",", ":"))
print(json.dumps({p: (v.get("titre") or v) for p, v in res["pays"].items()}, ensure_ascii=False)[:600])
