"""DEMANDE : ce que les gens cherchent en ce moment (recherches en forte hausse sur idealo FR, DE, ES, IT).

- tendances() : toutes les 6 h, met à jour data/demande.json (robot Apify saswave, plafond 0,10 $).
- est_demande(titre) : le titre d'un bon plan correspond-il à une recherche en hausse ? (gratuit)
- chasse_ciblee() : 1 fois par jour, pour les 3 recherches qui montent le plus en France, cherche sur
  Leboncoin et Vinted des annonces NEUVES nettement sous le prix idealo (occasion sous-cotée).
"""
import json
import os
from datetime import datetime, timedelta, timezone

from . import apify, comparateurs

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(RACINE, "data/demande.json")
apify.ROBOTS["idealo_tendances"] = ("saswave~idealo-trending-search-scraper", 0.10)


def _lire():
    try:
        return json.load(open(F, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _ecrire(d):
    os.makedirs(os.path.dirname(F), exist_ok=True)
    json.dump(d, open(F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _age(iso):
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return timedelta(days=99)


def tendances(force=False):
    d = _lire()
    if not force and _age(d.get("maj")) < timedelta(hours=6):
        return d
    items = apify.lancer("idealo_tendances", {"domains": ["idealo.fr", "idealo.de", "idealo.es", "idealo.it"]}, maxi=200)
    if not items:
        return d
    # idealo met 2147483647 quand la recherche est toute nouvelle : on plafonne à 1000 % (« nouveau »)
    liste = [{"recherche": i["query"], "popularite": i.get("popularity"), "hausse_pct": min(i.get("percentIncrease") or 0, 1000),
              "nouveau": (i.get("percentIncrease") or 0) >= 1000000,
              "pays": (i.get("domain") or "").split(".")[-1].upper()} for i in items if isinstance(i, dict) and i.get("query")]
    liste.sort(key=lambda x: -((x["popularite"] or 0) * (1 + (x["hausse_pct"] or 0) / 100)))
    d.update({"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "liste": liste})
    hist = d.setdefault("historique", [])
    hist.append({"maj": d["maj"], "top_fr": [x["recherche"] for x in liste if x["pays"] == "FR"][:15]})
    d["historique"] = hist[-120:]
    _ecrire(d)
    return d


def est_demande(titre, d=None):
    d = d or _lire()
    for x in d.get("liste", []):
        if comparateurs.correspond(titre, x["recherche"]):
            return x
    return None


def chasse_ciblee(regles, n=3):
    """Une fois par jour : bons plans d'occasion (neufs) sur les produits les plus demandés en France."""
    d = _lire()
    if _age(d.get("chasse_maj")) < timedelta(hours=24):
        return []
    trouves = []
    for x in [x for x in d.get("liste", []) if x["pays"] == "FR"][:n]:
        pi = apify.prix_idealo(x["recherche"])
        if not pi:
            continue
        rr = apify.revente_reelle(x["recherche"], pi["prix_min"] * 0.4)
        for canal, r in rr.items():
            if r["min"] <= pi["prix_min"] * 0.75:
                trouves.append({"recherche": x["recherche"], "hausse_pct": x["hausse_pct"], "canal": canal,
                                "annonce_min": r["min"], "nb_annonces": r["nb"], "idealo": pi})
    d["chasse_maj"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    d["chasse_resultats"] = trouves
    _ecrire(d)
    return trouves
