"""Veille 24h/24 : toutes les 30 minutes, lit les 17 sources, repère les TRÈS gros bons plans
(au moins 25 % sous le neuf le moins cher en France, ou erreur de prix probable) et les écrit dans
data/alertes.json avec le statut « a_verifier ». Claude les vérifie toutes les heures et prévient David.

Rapide et économe : pas d'équipe complète, une seule IA rapide (Groq) pour nommer les produits.
python -m denicheur.veille
"""
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import apify, collecte, comparateurs, demande, equipe
from .ia import Agent, extraire_json

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEUIL_ECART = 0.80          # prix d'achat <= 80 % du neuf le moins cher en France
MAXI_PRODUITS = 12          # produits vérifiés par tour (rythme poli pour les comparateurs)
SIGNAUX = re.compile(r"erreur de prix|price error|pricing error|preisfehler|error de precio|errore di prezzo|b[łl][aą]d cenowy|prijsfout", re.I)


def _lire(rel, defaut):
    try:
        with open(os.path.join(RACINE, rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return defaut


def _ecrire(rel, d):
    chemin = os.path.join(RACINE, rel)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


DEMANDE = {}


def priorite(a):
    p = (a.get("temperature") or 0)
    if demande.est_demande(a["titre"], DEMANDE):
        p += 300  # produit que les gens cherchent en ce moment : examiné en premier
    if SIGNAUX.search(a["titre"] + " " + (a.get("description") or "")):
        p += 500
    return p


def nommer(annonces):
    """Une IA rapide donne le nom exact (marque + modèle) de chaque produit. Sinon : titre nettoyé."""
    noms = {}
    conf = _lire("config/equipe.json", {})["agents"]["gptoss"]
    agent = Agent("gptoss", {**conf, "max_appels": 1})
    lignes = "\n".join(f'{a["id"]} | {a["titre"]}' for a in annonces)
    rep = agent.demander(
        "Tu identifies des produits. Réponds en json uniquement.",
        "Pour chaque ligne « id | titre d'annonce », donne le nom exact du produit : marque + modèle + "
        "capacité si utile, 2 à 6 mots, sans couleur, taille, texte promo ni nom de magasin. "
        "Si ce n'est pas un produit physique précis (lot, code promo, abonnement, sélection), mets null.\n"
        'Format json : {"produits": [{"id": "...", "nom": "..." }]}\n\n' + lignes)
    d = extraire_json(rep) if rep else None
    for x in (d or {}).get("produits", []):
        if isinstance(x, dict) and x.get("id") and x.get("nom"):
            noms[str(x["id"])] = str(x["nom"])[:60]
    return noms, agent


def tour():
    maintenant = datetime.now(timezone.utc)
    b = apify._budget()
    b["depense_ce_tour"] = 0
    os.makedirs(os.path.dirname(apify.F_BUDGET), exist_ok=True)
    json.dump(b, open(apify.F_BUDGET, "w"), indent=1)
    sources = [s for s in _lire("config/sources.json", {})["sources"] if s.get("actif", True)]
    regles = _lire("config/regles.json", {})
    DEMANDE.update(demande.tendances())
    annonces, etat = collecte.collecter(sources)
    vus = set(_lire("data/etat/vus_veille.json", []))
    nouvelles = [a for a in annonces if a["id"] not in vus]
    candidates = equipe.prefiltre(nouvelles, regles)
    candidates.sort(key=priorite, reverse=True)
    lot = candidates[:MAXI_PRODUITS]
    noms, agent = nommer(lot) if lot else ({}, None)
    alertes = _lire("data/alertes.json", [])
    deja = {x["id"] for x in alertes}
    nouvelles_alertes = []
    for a in lot:
        nom = noms.get(a["id"])
        signal = bool(SIGNAUX.search(a["titre"] + " " + (a.get("description") or "")))
        pp = comparateurs.prix_plancher(nom) if nom else None
        pmin = (pp or {}).get("prix_min")
        cout = equipe.cout_achat(a, regles)
        ecart = round(a["prix"] / pmin, 3) if pmin else None
        if a["id"] in deja:
            continue
        if (ecart is not None and ecart <= SEUIL_ECART and pmin >= 30) or (signal and (ecart is None or ecart <= 0.85)):
            x = {**{k: a.get(k) for k in ("id", "titre", "prix", "devise", "marchand", "lien", "pays", "source", "temperature", "categorie")},
                 "nom_produit": nom, "cout_achat": cout, "prix_plancher": pp, "ecart_vs_neuf_min": ecart,
                 "signal_erreur_prix": signal, "trouve_le": maintenant.isoformat(timespec="minutes"),
                 "statut": "a_verifier"}
            # contre-vérification automatique sur idealo (Apify) + prix réels Vinted / Leboncoin
            pi = apify.prix_idealo(nom) if nom else None
            if pi:
                x["idealo"] = pi
                x["ecart_vs_idealo"] = round(a["prix"] / pi["prix_min"], 3)
                if x["ecart_vs_idealo"] > 0.85 and not signal:
                    continue  # idealo montre que ce n'est pas une vraie affaire : on n'alerte pas
                x["prix_plancher"] = {"prix_min": min(pi["prix_min"], pmin or 1e9), "ou": "idealo", "lien": pi["lien"]}
            if nom:
                x["revente_reelle"] = apify.revente_reelle(nom, a["prix"])
            dm = demande.est_demande(a["titre"], DEMANDE)
            if dm:
                x["demande_forte"] = dm
            x["canaux"] = equipe.canaux_de_vente(x, regles)
            nouvelles_alertes.append(x)
    # chasse ciblée quotidienne sur les produits les plus demandés (occasion neuve sous-cotée)
    for t in demande.chasse_ciblee(regles):
        ident = "chasse-" + t["recherche"][:30].replace(" ", "-") + "-" + t["canal"]
        if ident not in deja:
            nouvelles_alertes.append({"id": ident, "titre": f'{t["recherche"]} : annonce {t["canal"]} à {t["annonce_min"]} € (idealo {t["idealo"]["prix_min"]} €)',
                                      "prix": t["annonce_min"], "devise": "EUR", "marchand": t["canal"], "lien": None,
                                      "pays": "FR", "source": "chasse_ciblee", "nom_produit": t["recherche"],
                                      "cout_achat": t["annonce_min"] + 5, "idealo": t["idealo"], "demande_forte": t,
                                      "trouve_le": maintenant.isoformat(timespec="minutes"), "statut": "a_verifier"})
    # ne marquer « vu » que ce qui a été examiné (le reste sera revu au prochain tour)
    vus.update(a["id"] for a in nouvelles if a not in candidates or a in lot)
    _ecrire("data/etat/vus_veille.json", sorted(vus)[-20000:])
    if nouvelles_alertes:
        _ecrire("data/alertes.json", (alertes + nouvelles_alertes)[-500:])
    bilan = {"heure": maintenant.astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M"),
             "annonces": len(annonces), "nouvelles": len(nouvelles), "examinees": len(lot),
             "nommees": len(noms), "alertes": len(nouvelles_alertes),
             "ia": {"appels": agent.appels, "reussites": agent.reussites, "erreurs": agent.erreurs[:2]} if agent else None,
             "sources_ko": [k for k, v in etat.items() if not v["ok"]],
             "apify_budget": apify._budget(),
             "demande_top_fr": [x["recherche"] for x in DEMANDE.get("liste", []) if x["pays"] == "FR"][:8]}
    # statistiques par catégorie (pour, dans quelques semaines, se concentrer sur les plus rentables)
    stats = _lire("data/stats_categories.json", {})
    for a in nouvelles:
        cat = (a.get("categorie") or "?").strip()[:60] or "?"
        st = stats.setdefault(cat, {"annonces": 0, "alertes": 0, "temperature_totale": 0})
        st["annonces"] += 1
        st["temperature_totale"] += max(0, a.get("temperature") or 0)
    for x in nouvelles_alertes:
        stats.setdefault((x.get("categorie") or "?").strip()[:60] or "?", {"annonces": 0, "alertes": 0, "temperature_totale": 0})["alertes"] += 1
    _ecrire("data/stats_categories.json", stats)
    journal = _lire("data/veille_journal.json", [])
    _ecrire("data/veille_journal.json", (journal + [bilan])[-200:])
    print(json.dumps(bilan, ensure_ascii=False))
    for x in nouvelles_alertes:
        print("ALERTE", x["titre"][:80], x["prix"], "neuf min", (x["prix_plancher"] or {}).get("prix_min"))


if __name__ == "__main__":
    tour()
