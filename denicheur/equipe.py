"""Travail de l'équipe : tri, analyse par les 4 analystes, calcul de marge, consensus."""
import json
import math
import re
import statistics
import time

from .ia import extraire_json

EXCLUS = re.compile(
    r"gratuit|offert|abonnement|forfait|carte sim|\bsim\b|code promo|cashback|remboursement|"
    r"carte cadeau|e-carte|bon d'achat|jeu concours|concours|sample|téléchargement|dématérialis|"
    r"steam key|clé steam|epic games|game pass|ps plus|netflix|spotify|disney\+|deezer|canal\+|"
    r"assurance|crédit|banque|parrainage|voyage|hôtel|vol |billet|restaurant|livraison offerte|par mois|/mois|freebox|box internet",
    re.I,
)

DOMAINES = {"tech", "gaming", "maison", "cuisine", "jardin-bricolage", "sport", "auto-moto", "mode",
            "puericulture-jouets", "beaute-sante", "animaux", "vintage-collection", "autre"}


def prefiltre(annonces, regles):
    garde = []
    for a in annonces:
        p = a.get("prix")
        if p is None or not (regles["prix_min"] <= p <= regles["prix_max"]):
            continue
        if EXCLUS.search(a["titre"]) or EXCLUS.search(a.get("categorie") or ""):
            continue
        garde.append(a)
    garde.sort(key=lambda a: a.get("temperature") or 0, reverse=True)
    return garde


def _ligne(a):
    prix = f"{a['prix']:.2f} {'£' if a['devise'] == 'GBP' else '€'}"
    return f"{a['id']} | {a['titre']} | {prix} | {a.get('marchand') or '?'} | {a.get('categorie') or '?'} | {a['pays']} | {a.get('temperature') or '?'}°"


def lots(liste, taille):
    return [liste[i:i + taille] for i in range(0, len(liste), taille)]


def trier(agent, annonces, taille_lot):
    """Le trieur ne garde que les produits physiques revendables. Si la tâche échoue, on garde tout."""
    systeme = ("Tu tries des bons plans pour un revendeur. Garde uniquement les PRODUITS PHYSIQUES qui "
               "pourraient être revendus avec bénéfice. Écarte services, alimentaire, offres locales, "
               "produits très courants sans intérêt. Réponds uniquement en JSON : {\"garder\": [\"id\", ...]}")
    gardes, ok = [], True
    for lot in lots(annonces, taille_lot * 2):
        rep = agent.demander(systeme, "Bons plans (id | titre | prix | marchand | catégorie | pays | popularité) :\n" + "\n".join(_ligne(a) for a in lot))
        data = extraire_json(rep)
        if not data or not isinstance(data.get("garder"), list):
            ok = False
            gardes.extend(lot)  # en cas d'échec, on ne perd rien
            continue
        ids = set(map(str, data["garder"]))
        gardes.extend(a for a in lot if a["id"] in ids)
    return gardes, ok


def analyser(agent, annonces, methode, taille_lot):
    """Un analyste étudie les mêmes lots que les autres. Retourne la liste de ses choix validés."""
    ids_valides = {a["id"] for a in annonces}
    choix = []
    taille = agent.conf.get("taille_lot", taille_lot)  # certaines IA (Groq) acceptent moins de texte par minute
    for n, lot in enumerate(lots(annonces, taille)):
        if not agent.disponible():
            break
        if n and agent.conf.get("pause"):
            time.sleep(agent.conf["pause"])
        rep = agent.demander(methode, "Bons plans du jour (id | titre | prix | marchand | catégorie | pays | popularité) :\n"
                             + "\n".join(_ligne(a) for a in lot))
        data = extraire_json(rep)
        if not data or not isinstance(data.get("choix"), list):
            if rep is not None:
                agent.erreurs.append("réponse non JSON ou mal formée")
            continue
        for c in data["choix"]:
            if not isinstance(c, dict) or str(c.get("id")) not in ids_valides:
                continue
            try:
                prix_rev = float(c.get("prix_revente_estime"))
            except (TypeError, ValueError):
                continue
            if prix_rev <= 0:
                continue
            choix.append({
                "id": str(c["id"]),
                "agent": agent.id,
                "domaine": c.get("domaine") if c.get("domaine") in DOMAINES else "autre",
                "plateforme_revente": str(c.get("plateforme_revente") or "amazon").lower(),
                "etat_revente": c.get("etat_revente") or "neuf",
                "prix_revente_estime": prix_rev,
                "demande": _borne(c.get("demande"), 1, 5, 3),
                "concurrence": _borne(c.get("concurrence"), 1, 5, 3),
                "mode": c.get("mode") if c.get("mode") in ("stock", "dropshipping") else "stock",
                "confiance": _borne(c.get("confiance"), 0, 1, 0.5),
                "erreur_prix": bool(c.get("erreur_prix")),
                "raison": str(c.get("raison") or "")[:240],
            })
    return choix


def _borne(v, mini, maxi, defaut):
    try:
        return max(mini, min(maxi, float(v)))
    except (TypeError, ValueError):
        return defaut


def cout_achat(annonce, regles):
    prix = annonce["prix"]
    if annonce["devise"] == "GBP":
        prix *= regles.get("taux_gbp_eur", 1.15)
    cout = prix + regles["port_achat_defaut"]
    if annonce["pays"] == "UK":  # import hors UE : TVA française + droit forfaitaire 3 €
        cout += prix * 0.20 + 3.0
    return round(cout, 2)


def marge_nette(prix_revente, plateforme, cout, regles):
    p = regles["plateformes_revente"].get(plateforme) or regles["plateformes_revente"]["amazon"]
    net_vente = prix_revente * (1 - p["commission"]) - p["frais_fixes"] - p["port"]
    return round(net_vente - cout, 2)


def consolider(annonces, tous_choix, regles):
    par_id = {a["id"]: a for a in annonces}
    groupes = {}
    for c in tous_choix:
        groupes.setdefault(c["id"], []).append(c)
    candidats = []
    for ident, choix in groupes.items():
        a = par_id[ident]
        cout = cout_achat(a, regles)
        prix_rev = statistics.median(c["prix_revente_estime"] for c in choix)
        plateforme = statistics.mode(c["plateforme_revente"] for c in choix)
        marge = marge_nette(prix_rev, plateforme, cout, regles)
        rentab = round(marge / cout, 3) if cout else 0
        demande = statistics.mean(c["demande"] for c in choix)
        concurrence = statistics.mean(c["concurrence"] for c in choix)
        confiance = statistics.mean(c["confiance"] for c in choix)
        consensus = len({c["agent"] for c in choix})
        score = max(0.0, rentab) * 100 * (0.6 + 0.2 * consensus) * confiance * (demande / 3) * (1.3 - 0.1 * concurrence)
        candidats.append({
            **{k: a[k] for k in ("id", "titre", "prix", "devise", "marchand", "lien", "pays", "source", "temperature")},
            "domaine": statistics.mode(c["domaine"] for c in choix),
            "plateforme_revente": plateforme,
            "prix_revente_estime": round(prix_rev, 2),
            "cout_achat": cout,
            "marge_nette": marge,
            "rentabilite": rentab,
            "demande": round(demande, 1),
            "concurrence": round(concurrence, 1),
            "consensus": consensus,
            "agents": sorted({c["agent"] for c in choix}),
            "mode": statistics.mode(c["mode"] for c in choix),
            "erreur_prix": any(c["erreur_prix"] for c in choix),
            "raisons": {c["agent"]: c["raison"] for c in choix},
            "score": round(score, 1),
        })
    s = regles["seuils"]
    retenus = [c for c in candidats if c["marge_nette"] >= s["marge_nette_min"] and c["rentabilite"] >= s["rentabilite_min"]
               and c["consensus"] >= s["consensus_min"]]
    retenus.sort(key=lambda c: c["score"], reverse=True)
    return retenus, candidats


def nb_appels_prevus(n, taille):
    return math.ceil(n / taille) if n else 0
