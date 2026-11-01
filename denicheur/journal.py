"""Journal de TOUTES les recherches, cumulé par jour : qui (dénicheur A/B/C), où (source/robot),
quoi (produit/catégorie), combien ça coûte, ce que ça rapporte.
Fichier par jour : data/journal/AAAA-MM-JJ.json — sert au rapport « Recherches et coûts »."""
import glob
import json
import os
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(RACINE, "data/journal")


def _f(jour):
    return os.path.join(D, f"{jour}.json")


def noter(denicheur, source, cible, cout_usd=0.0, resultats=0, alertes=0, categorie=None):
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        d = json.load(open(_f(jour), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    cle = " | ".join([denicheur, source, (cible or "")[:80], (categorie or "")[:60]])
    x = d.setdefault(cle, {"denicheur": denicheur, "source": source, "cible": (cible or "")[:80],
                           "categorie": (categorie or "")[:60], "recherches": 0, "cout_usd": 0.0, "resultats": 0, "alertes": 0})
    x["recherches"] += 1
    x["cout_usd"] = round(x["cout_usd"] + cout_usd, 4)
    x["resultats"] += resultats
    x["alertes"] += alertes
    os.makedirs(D, exist_ok=True)
    json.dump(d, open(_f(jour), "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def lire(jours=30):
    limite = (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%d")
    out = []
    for f in sorted(glob.glob(os.path.join(D, "*.json"))):
        jour = os.path.basename(f)[:-5]
        if jour >= limite:
            try:
                for x in json.load(open(f, encoding="utf-8")).values():
                    out.append({**x, "jour": jour})
            except (OSError, json.JSONDecodeError):
                continue
    return out
