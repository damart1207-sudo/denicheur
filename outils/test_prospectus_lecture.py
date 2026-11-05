"""Test réel (≈ 12 pages Gemini, quelques centimes) : lecture des prospectus Lidl et Action par Gemini.
-> data/prospectus.json      Lancement : outil = test_prospectus_lecture"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import prospectus  # noqa: E402
for ens in ("Lidl", "Action"):
    try:
        l = prospectus.prospectus_enseigne(ens)
        print(ens, "prospectus :", [(c, n, len(u), u[:1]) for c, n, u in l[:3]])
    except Exception as e:
        print(ens, "ERREUR", e)
print(prospectus.tour(["Boulanger", "Darty", "Action", "Gifi", "Brico-Depot", "Decathlon", "King-Jouet", "Lidl"], pages_jour=16))
for p in json.load(open(prospectus.F_SORTIE))["produits"][:25]:
    print(" ", p["marchand"], "|", p["titre"][:60], "|", p["prix"], "| avant", p.get("prix_avant"), "|", p.get("valable_du"), "→", p.get("valable_au"))
