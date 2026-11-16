"""ÉCART VENDEURS (demande de David, 16/11/2026 — cas de l'écran iiyama : 1er vendeur 92,19 €, 2e 142,59 €).

Pour les baisses neuves du radar Amazon du jour : les offres neuves en cours (Keepa), triées prix + port.
Une affaire = au moins ECART_MIN euros entre le vendeur le moins cher et le SECOND, à condition que le prix du second
soit cohérent avec la moyenne des 90 jours (sinon c'est un prix fantaisiste : carnet à 185 €, bibliothèque à 338 €,
constatés au test du 16/11).
Chaque affaire est analysée : ventes (achats du mois affichés par Amazon, ventes estimées sur 30 jours, classement),
volume de recherche Google (appel groupé DataForSEO, plafonds existants), et DEUX marges à un prix de revente
intermédiaire sur Leboncoin : sans charges, et avec les charges de la micro-entreprise (config/regles.json).
Alerte Telegram par affaire, une seule fois par jour et par prix.

Garde-fous : PRODUITS_TOUR produits par tour (14 jetons Keepa chacun au plus, compris dans l'abonnement), réserve et
plafonds du moissonneur respectés, au plus un appel DataForSEO groupé (0,09 $) toutes les 2 heures, aucun achat.
-> data/ecarts.json
"""
import json
import os
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_ECARTS = os.path.join(RACINE, "data/ecarts.json")
F_VUS = os.path.join(RACINE, "data/etat/ecart_vus.json")
ECART_MIN = 50            # euros entre le 1er et le 2e vendeur
PRIX_MIN = 40
BAISSE_MIN = 45           # euros sous la moyenne 90 jours pour mériter les 14 jetons
COHERENCE = (0.70, 1.35)  # le 2e vendeur doit être entre 70 % et 135 % de la moyenne 90 jours
PRODUITS_TOUR, COUT_PRODUIT, ALERTES_TOUR = 8, 14, 5
NET_VISE = 30             # marge nette que David vise


def _lire(f, d):
    try:
        with open(f, encoding="utf-8") as g:
            return json.load(g)
    except (OSError, json.JSONDecodeError):
        return d


def _ecrire(f, d):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", encoding="utf-8") as g:
        json.dump(d, g, ensure_ascii=False, indent=1)


def offres_neuves(p):
    """Offres neuves EN COURS d'un produit Keepa (demandé avec offers=20) : [{total, amazon, fba}] triées."""
    offres = p.get("offers") or []
    vivantes = p.get("liveOffersOrder")
    if isinstance(vivantes, list):
        offres = [offres[i] for i in vivantes if isinstance(i, int) and 0 <= i < len(offres)]
    out = []
    for o in offres:
        if not isinstance(o, dict) or o.get("condition") != 1:
            continue
        h = o.get("offerCSV") or []
        if len(h) < 3 or not isinstance(h[-2], (int, float)) or h[-2] <= 0:
            continue
        port = h[-1] if isinstance(h[-1], (int, float)) and h[-1] > 0 else 0
        out.append({"total": round((h[-2] + port) / 100, 2), "amazon": bool(o.get("isAmazon")), "fba": bool(o.get("isFBA"))})
    return sorted(out, key=lambda x: x["total"])


def mot_cle(titre, marque=None):
    """Nom court pour le volume de recherche : marque + les premiers mots du titre (4 mots au plus)."""
    from .chaine import requete_google
    return " ".join(requete_google(titre, marque).lower().split()[:4])


def marges(achat, second, regles):
    """Deux marges au prix intermédiaire (milieu entre le 1er et le 2e vendeur), sur Leboncoin (0 commission)."""
    from .rentabilite import DEFAUT, calculer
    fiscal = {**DEFAUT, **regles.get("fiscalite", {})}
    taux = fiscal["cotisations"] + fiscal["versement_liberatoire"] + fiscal["formation_professionnelle"]
    prix = float(round((achat + second) / 2))
    avec = calculer(prix, "leboncoin", achat, regles)
    pour_net_avec = round((achat + fiscal["provision_incident_eur"] + NET_VISE) / (1 - taux), 2)
    return {"prix_revente": prix, "sous_le_second_pct": round((1 - prix / second) * 100),
            "marge_sans_charges": round(prix - achat, 2), "marge_avec_charges": avec["marge_nette"],
            "charges_micro": avec["prelevements"], "provision": avec["provision"],
            f"prix_pour_{NET_VISE}_net_sans_charges": round(achat + NET_VISE, 2),
            f"prix_pour_{NET_VISE}_net_avec_charges": pour_net_avec,
            f"{NET_VISE}_net_possible_avec_charges": pour_net_avec < second}


def analyser(p, a, regles):
    """p : produit Keepa (offers=20, stats=90). a : ligne du radar. Renvoie la fiche, avec 'retenu' vrai ou la raison."""
    lignes = offres_neuves(p)
    st = p.get("stats") or {}
    cur = st.get("current") or []
    rang = cur[3] if len(cur) > 3 and isinstance(cur[3], int) and cur[3] > 0 else a.get("rang")
    f = {"asin": a["asin"], "titre": (p.get("title") or a.get("titre") or "")[:140], "marque": p.get("brand"), "lien": a.get("lien"),
         "moyenne_90j": a.get("moyenne_90j"), "nb_offres_neuves": len(lignes), "offres": lignes[:4], "rang": rang,
         "achetes_mois_amazon": p.get("monthlySold") if isinstance(p.get("monthlySold"), int) else None,
         "ventes_estimees_30j": st.get("salesRankDrops30") if isinstance(st.get("salesRankDrops30"), int) else None,
         "vu": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "retenu": False}
    if len(lignes) < 2:
        f["raison"] = "un seul vendeur neuf : pas de second prix"
        return f
    premier, second = lignes[0], lignes[1]
    f.update({"premier": premier["total"], "premier_amazon": premier["amazon"], "second": second["total"],
              "ecart": round(second["total"] - premier["total"], 2)})
    if f["ecart"] < ECART_MIN:
        f["raison"] = f"écart de {f['ecart']} € seulement"
        return f
    ref = a.get("moyenne_90j")
    if not ref or not (COHERENCE[0] * ref <= second["total"] <= COHERENCE[1] * ref):
        f["raison"] = f"prix du 2e vendeur incohérent avec la moyenne 90 jours ({ref} €)"
        return f
    f["mot_cle"] = mot_cle(f["titre"], f["marque"])
    f["marges"] = marges(premier["total"], second["total"], regles)
    f["retenu"] = True
    return f


def _eur(v):
    return f"{v:.2f}".replace(".", ",") + " €" if isinstance(v, (int, float)) else "—"


def message(f):
    m = f["marges"]
    ventes = []
    if f.get("achetes_mois_amazon"):
        ventes.append(f"{f['achetes_mois_amazon']}+ achetés le mois dernier (Amazon)")
    if f.get("ventes_estimees_30j") is not None:
        ventes.append(f"≈ {f['ventes_estimees_30j']} ventes sur 30 j")
    if f.get("rang"):
        ventes.append(f"classement {f['rang']}")
    from html import escape
    t = [f"🔎 <b>ÉCART VENDEURS</b> — {escape(f['titre'][:110])}",
         f"1er vendeur : <b>{_eur(f['premier'])}</b>{' (Amazon)' if f.get('premier_amazon') else ''} · 2e : {_eur(f['second'])} · écart <b>{_eur(f['ecart'])}</b>",
         f"Moyenne 90 j : {_eur(f.get('moyenne_90j'))} · {f['nb_offres_neuves']} vendeurs en neuf"]
    if ventes:
        t.append("Ventes : " + " · ".join(ventes))
    if f.get("volume") is not None:
        t.append(f"Recherches Google : {f['volume']}/mois (« {escape(f['mot_cle'])} »)")
    n = NET_VISE
    possible = m[f"{n}_net_possible_avec_charges"]
    t += [f"Revente à {_eur(m['prix_revente'])} sur Leboncoin ({m['sous_le_second_pct']} % sous le 2e vendeur) :",
          f" • sans charges : <b>{_eur(m['marge_sans_charges'])}</b>",
          f" • avec charges micro : <b>{_eur(m['marge_avec_charges'])}</b>",
          f"Pour {n} € nets : {_eur(m[f'prix_pour_{n}_net_sans_charges'])} sans charges, {_eur(m[f'prix_pour_{n}_net_avec_charges'])} avec charges"
          + ("" if possible else " (au-dessus du 2e vendeur)"),
          f.get("lien") or ""]
    return "\n".join(t)


def candidats(vus):
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = []
    for a in _lire(os.path.join(RACINE, "data/radar_amazon.json"), {}).get("affaires", []):
        prix, moy = a.get("prix") or 0, a.get("moyenne_90j") or 0
        if a.get("type") != "neuf" or (a.get("vu") or "")[:10] != jour or prix < PRIX_MIN or moy - prix < BAISSE_MIN or moy > prix * 3:
            continue
        v = vus.get(a["asin"]) or {}
        if v.get("jour") == jour and abs((v.get("prix") or 0) - prix) < 1:
            continue  # déjà examiné aujourd'hui à ce prix
        out.append(a)
    return sorted(out, key=lambda a: -(a["moyenne_90j"] - a["prix"]))


def tour(etat, maxi=PRODUITS_TOUR):
    """Un tour : examine jusqu'à `maxi` baisses du radar, analyse et alerte. Renvoie le nombre d'affaires retenues."""
    from . import moisson, telegram
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    vus = {k: v for k, v in _lire(F_VUS, {}).items() if v.get("jour") == jour}
    regles = _lire(os.path.join(RACINE, "config/regles.json"), {})
    base = _lire(F_ECARTS, {})
    if base.get("jour") != jour:
        base = {"jour": jour, "examines": 0, "affaires": []}
    retenus = []
    for a in candidats(vus)[:maxi]:
        try:
            d = moisson._appel("product", {"domain": 4, "asin": a["asin"], "offers": 20, "stats": 90, "history": 0},
                               etat=etat, cout_max=COUT_PRODUIT)
        except moisson.BudgetKeepaInsuffisant:
            break
        except Exception:
            continue
        p = (d.get("products") or [None])[0]
        vus[a["asin"]] = {"jour": jour, "prix": a["prix"]}
        if not isinstance(p, dict):
            continue
        base["examines"] += 1
        f = analyser(p, a, regles)
        if f["retenu"]:
            retenus.append(f)
    if retenus:
        from . import fiche
        vol = fiche.completer_volumes([{"nom_produit": f["mot_cle"]} for f in retenus])
        deja = {x["asin"]: x for x in base["affaires"]}
        envoyes = 0
        for f in sorted(retenus, key=lambda f: -f["marges"]["marge_avec_charges"]):
            v = vol.get(f["mot_cle"])
            f["volume"] = v.get("v") if isinstance(v, dict) else None
            ancien = deja.get(f["asin"])
            if envoyes < ALERTES_TOUR and not (ancien and ancien.get("alerte") and abs(ancien.get("premier", 0) - f["premier"]) < 1):
                f["alerte"] = telegram.envoyer(message(f))
                envoyes += 1
            elif ancien:
                f["alerte"] = ancien.get("alerte")
            deja[f["asin"]] = f
        base["affaires"] = sorted(deja.values(), key=lambda f: -f["marges"]["marge_avec_charges"])
    base["maj"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    _ecrire(F_ECARTS, base)
    _ecrire(F_VUS, vus)
    return len(retenus)
