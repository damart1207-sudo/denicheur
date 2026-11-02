"""DEMANDE : ce que les gens cherchent en ce moment (recherches en forte hausse sur idealo FR, DE, ES, IT).

- tendances() : toutes les 12 h, met à jour data/demande.json (robot Apify saswave, plafond 0,10 $).
- est_demande(titre) : le titre d'un bon plan correspond-il à une recherche en hausse ? (gratuit)
- chasse_ciblee() : 1 fois par jour, pour les 3 recherches qui montent le plus en France, cherche sur
  Leboncoin et Vinted des annonces NEUVES nettement sous le prix idealo (occasion sous-cotée).
"""
import json
import os
from datetime import datetime, timedelta, timezone

from .ia import est_le_produit
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
    if not force and _age(d.get("maj")) < timedelta(hours=12):
        return d
    apify.CONTEXTE["denicheur"] = "B"
    items = apify.lancer("idealo_tendances", {"domains": ["idealo.fr", "idealo.de", "idealo.es", "idealo.it"]}, maxi=200)
    apify.CONTEXTE["denicheur"] = "A"
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


def _annonces_A():
    try:
        return json.load(open(os.path.join(RACINE, "data/etat/annonces_recentes.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def chasse_ciblee(regles, n=3):
    """Dénicheur C, une fois par jour après la mise à jour de la demande (B) :
    pour les n produits les plus demandés en France, regarde d'abord si le dénicheur A a déjà vu un bon plan ;
    sinon cherche lui-même (idealo + Leboncoin + Vinted)."""
    d = _lire()
    if _age(d.get("chasse_maj")) < timedelta(hours=24):
        return []
    apify.CONTEXTE["denicheur"] = "C"
    trouves = []
    vus_A = _annonces_A()
    for x in [x for x in d.get("liste", []) if x["pays"] == "FR"][:n]:
        q = x["recherche"]
        deja_A = [a for a in vus_A if a.get("prix") and comparateurs.correspond(a["titre"], q)]
        pi = apify.prix_idealo(q)
        if not pi:
            continue
        # le prix idealo doit concerner le produit recherché lui-même (pas un jeu ou un accessoire)
        try:
            if est_le_produit(pi.get("titre") or "", q) is not True:
                continue
        except Exception:
            continue
        if deja_A:  # A l'a déjà vu : on vérifie juste si son prix bat idealo
            for a in deja_A:
                if a["prix"] <= pi["prix_min"] * 0.85 and a["prix"] >= pi["prix_min"] * 0.3:
                    try:
                        if est_le_produit(a["titre"], q) is not True:
                            continue  # jeu, accessoire, carte… : ce n'est pas le produit recherché
                    except Exception:
                        continue
                    trouves.append({"recherche": q, "hausse_pct": x["hausse_pct"], "canal": "dénicheur A : " + (a.get("marchand") or a.get("source") or "?"),
                                    "annonce_min": a["prix"], "lien": a.get("lien"), "nb_annonces": 1, "idealo": pi, "par": "A"})
            continue
        rr = apify.revente_reelle(q, pi["prix_min"] * 0.4)
        for canal, r in rr.items():
            if pi["prix_min"] * 0.3 <= r["min"] <= pi["prix_min"] * 0.75:
                trouves.append({"recherche": q, "hausse_pct": x["hausse_pct"], "canal": canal, "annonce_min": r["min"],
                                "lien": r.get("lien_min"), "nb_annonces": r["nb"], "idealo": pi, "par": "C"})
    apify.CONTEXTE["denicheur"] = "A"
    d["chasse_maj"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    d["chasse_resultats"] = trouves
    _ecrire(d)
    return trouves
