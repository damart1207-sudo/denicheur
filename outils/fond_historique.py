"""Produits de fond : historique complet Keepa (toutes les années) des candidats de config/fond_candidats.json.
Coût : 1 jeton Keepa par produit (compris dans l'abonnement, aucun euro en plus). Aucun autre service appelé.
Garde-fous : 25 min au plus, s'arrête seul, n'attend jamais plus de 90 s d'affilée. outil = fond_historique
Sortie : data/fond_historique.json (par produit et par mois : rang moyen, prix neuf moyen, nb de vendeurs, ventes/mois Amazon)."""
import json, os, sys, time
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import keepa

DEBUT, LIMITE, LOT = time.time(), 25 * 60, 20
SORTIE = "data/fond_historique.json"


def ts(m):  # minute Keepa -> secondes unix
    return (m + 21564000) * 60


def par_mois(csv, diviseur=1, fin=None):
    """Moyenne pondérée par le temps, mois par mois, d'une série Keepa [t, v, t, v…] (v = -1 : pas de donnée)."""
    if not csv or len(csv) < 2:
        return {}
    fin = fin or time.time()
    cumul = {}
    pts = [(ts(csv[i]), csv[i + 1]) for i in range(0, len(csv) - 1, 2)]
    for k, (t0, v) in enumerate(pts):
        t1 = pts[k + 1][0] if k + 1 < len(pts) else fin
        if v is None or v < 0 or t1 <= t0:
            continue
        t = t0
        while t < t1:  # découpe l'intervalle aux frontières de mois
            d = datetime.fromtimestamp(t, timezone.utc)
            suiv = datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=timezone.utc).timestamp()
            bout = min(t1, suiv)
            c = cumul.setdefault(d.strftime("%Y-%m"), [0.0, 0.0])
            c[0] += v * (bout - t); c[1] += bout - t
            t = bout
    return {m: round(s / d / diviseur, 2) for m, (s, d) in sorted(cumul.items()) if d > 0}


def main():
    cands = json.load(open("config/fond_candidats.json"))["produits"]
    try:
        res = json.load(open(SORTIE))
    except (OSError, json.JSONDecodeError):
        res = {"produits": {}}
    faits = res["produits"]
    reste = [c["asin"] for c in cands if c["asin"] not in faits]
    jetons, erreurs = None, []
    while reste and time.time() - DEBUT < LIMITE:
        lot = reste[:LOT]
        try:
            d = keepa._lire({"key": keepa.cle(), "domain": 4, "asin": ",".join(lot), "stats": 365, "history": 1})
        except Exception as e:
            erreurs.append(f"{type(e).__name__}: {str(e)[:200]}")
            if len(erreurs) >= 4:
                break
            time.sleep(60)  # le plus souvent : réserve de jetons vide (HTTP 429)
            continue
        jetons = d.get("tokensLeft")
        if d.get("error"):
            erreurs.append(str(d["error"])[:200])
        for p in d.get("products") or []:
            csv = p.get("csv") or []
            g = lambda i: csv[i] if len(csv) > i else None
            faits[p.get("asin")] = {
                "t": (p.get("title") or "")[:120], "marque": p.get("brand"),
                "suivi_depuis": datetime.fromtimestamp(ts(p["trackingSince"]), timezone.utc).strftime("%Y-%m") if p.get("trackingSince") else None,
                "en_vente_depuis": datetime.fromtimestamp(ts(p["listedSince"]), timezone.utc).strftime("%Y-%m") if p.get("listedSince") else None,
                "rang": par_mois(g(3)), "prix_neuf": par_mois(g(1), 100), "prix_amazon": par_mois(g(0), 100),
                "nb_vendeurs_neuf": par_mois(g(11)), "vendus_mois": par_mois(p.get("monthlySoldHistory")),
                "vendus_mois_actuel": p.get("monthlySold"),
            }
        reste = [a for a in reste if a not in lot]
        res.update({"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "jetons_restants": jetons, "restants": len(reste), "erreurs": erreurs[-5:]})
        json.dump(res, open(SORTIE, "w"), ensure_ascii=False, separators=(",", ":"))
        print(f"{len(faits)} produits faits, {len(reste)} restants, jetons {jetons}")
        if reste and isinstance(jetons, int) and jetons < LOT:
            time.sleep(62)  # la réserve se remplit d'environ 20 jetons par minute
    res.update({"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "restants": len(reste), "erreurs": erreurs[-5:]})
    json.dump(res, open(SORTIE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"FIN : {len(faits)} produits, {len(reste)} restants, erreurs {erreurs[-3:]}")


if __name__ == "__main__":
    main()
