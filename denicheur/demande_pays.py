"""RAPPORT DEMANDE PAR PAYS (Amigo, une fois par semaine) : pour les produits de la base (mots-clés Google écrits par
Gemini), volume de recherche mensuel dans 6 pays (FR, DE, ES, IT, US, JP) croisé avec le prix Amazon du produit
-> tranches de prix (0-50, 50-100, 100-300, 300-600, 600+ €) : où les gens cherchent quoi, et à quel prix.
Coût : 1 appel DataForSEO par pays (≈ 0,09 $ chacun, ≤ 1 000 mots-clés) = ≈ 0,55 $ par semaine. Aucun achat.
-> data/demande_pays.json (onglet « Demande par pays » du rapport) ;  python -m denicheur.demande_pays"""
import json
import os
from datetime import datetime, timezone

from . import bingo, dataforseo, sante

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(RACINE, "data/demande_pays.json")
PAYS = ("FR", "DE", "ES", "IT", "US", "JP")
TRANCHES = ((0, 50), (50, 100), (100, 300), (300, 600), (600, 10**6))


def tranche(prix):
    for a, b in TRANCHES:
        if a <= (prix or 0) < b:
            return f"{a}-{b} €" if b < 10**6 else f"{a} € et plus"
    return "inconnue"


def semaine(maxi_mots=1000):
    cands = bingo.candidats()
    mots = list(cands)[:maxi_mots]
    if not mots:
        print("demande_pays : aucun mot-clé")
        return
    res = {"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "nb_mots": len(mots), "pays": {}}
    for p in PAYS:
        vols = sante.protege(f"demande_pays {p}", dataforseo.volumes, mots, p, defaut={})
        lignes = []
        for m in mots:
            v = (vols.get(m) or {}).get("volume_mensuel")
            if v:
                c = cands[m]
                lignes.append({"mot_cle": m, "volume": v, "prix": c.get("prix"), "tranche": tranche(c.get("prix")),
                               "vendeurs_amazon_fr": c.get("vendeurs"), "asin": c.get("asin"), "titre": (c.get("titre") or "")[:80]})
        lignes.sort(key=lambda x: -x["volume"])
        par_tranche = {}
        for x in lignes:
            t = par_tranche.setdefault(x["tranche"], {"produits": 0, "recherches": 0})
            t["produits"] += 1
            t["recherches"] += x["volume"]
        res["pays"][p] = {"nb_avec_volume": len(lignes), "top": lignes[:60], "tranches": par_tranche}
        print(f"  {p} : {len(lignes)} produits avec volume ; tranches {par_tranche}")
    os.makedirs(os.path.dirname(F), exist_ok=True)
    json.dump(res, open(F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"demande_pays : {len(mots)} mots-clés, {len(PAYS)} pays")


if __name__ == "__main__":
    semaine()
