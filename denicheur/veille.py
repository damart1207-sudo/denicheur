"""Veille 24h/24 : toutes les 30 minutes, lit les 17 sources, repère les TRÈS gros bons plans
(au moins 25 % sous le neuf le moins cher en France, ou erreur de prix probable) et les écrit dans
data/alertes.json avec le statut « a_verifier ». Claude les vérifie toutes les heures et prévient David.

Rapide et économe : pas d'équipe complète, une seule IA rapide (Gemini) pour nommer les produits.
python -m denicheur.veille
"""
import json
import hashlib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import apify, base, collecte, comparateurs, demande, equipe, journal, lecteur, sante
from .ia import Agent, extraire_json
from .meme_produit import public_different

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEUIL_ECART = 0.85          # bon plan : prix <= 85 % du neuf le moins cher en France (au moins 15 % d'économie)
MAXI_PRODUITS = 25          # produits vérifiés par tour (≈ 10 s chacun) ; le BUDGET ci-dessous arrête le tour avant la coupure
BUDGET_EXAMEN_S = 400       # secondes accordées à l'examen des produits (le workflow coupe à 600 s : il reste 3 min pour relire les pages et écrire)
BUDGET_TOUR_S = 520         # au-delà, plus aucune lecture de page : on écrit et on sort
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


def empreinte(a):
    """Un changement de prix doit être examiné même si l'identifiant est stable."""
    valeurs = [a.get(k) for k in ("id", "prix", "devise", "pays", "titre")]
    return hashlib.sha256(json.dumps(valeurs, ensure_ascii=False).encode()).hexdigest()


def identifier_asin(a):
    """Extraire uniquement un identifiant explicite d'un lien Amazon."""
    lien = a.get("lien_marchand") or a.get("lien") or ""
    m = re.search(r"https?://(?:www\.)?amazon\.[a-z.]+/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?#]|$)", lien, re.I)
    if m and not a.get("asin"):
        a["asin"] = m.group(1).upper()


def a_revoir(a, vus, maintenant):
    precedent = vus.get(a["id"], {})
    return (precedent.get("empreinte") != empreinte(a)
            or precedent.get("prochain", "") <= maintenant.isoformat())


def annonces_keepa():
    """Lire les récoltes locales : aucun appel fournisseur supplémentaire."""
    from . import moisson, arbitrage
    return (sante.protege("radar vers veille", moisson.annonces_radar, maxi=12, defaut=[]) or []) + (
        sante.protege("arbitrage vers veille", arbitrage.annonces_arbitrage, maxi=8, defaut=[]) or [])


def priorite(a):
    p = (a.get("temperature") or 0)
    dm = demande.est_demande(a["titre"], DEMANDE)
    if dm:
        p += 300  # produit que les gens cherchent en ce moment : examiné en premier
        if str(dm.get("origine", "")) in ("bingo", "david") or str(dm.get("origine", "")).startswith("hype"):
            p += 400  # liste de chasse d'Amigo (bingo / hype étrangère) : tout en haut de la pile
    if SIGNAUX.search(a["titre"] + " " + (a.get("description") or "")):
        p += 500
    return p


def nommer(annonces):
    """Une IA rapide donne le nom exact (marque + modèle) de chaque produit. Sinon : titre nettoyé."""
    noms = {}
    # Gemini (niveau payant, quelques centimes/jour) : les 120 appels quotidiens de la veille vidaient le quota Groq
    # (200 000 jetons/jour) dont le tribunal de nuit a besoin.
    # Gemini d'abord ; s'il refuse (402 paiement, quota), relais par les IA gratuites (NVIDIA, Z.ai, OpenRouter),
    # jamais Groq (réservé au tribunal de nuit). Sans nom, Idéfix ne peut rien comparer : le relais est vital.
    agents_conf = _lire("config/equipe.json", {})["agents"]
    lignes = "\n".join(f'{a["id"]} | {a["titre"]}' for a in annonces)
    d, agent = None, None
    for ident in ("gemini", "deepseek", "glm", "nemotron_nv", "gemma"):
        conf = agents_conf.get(ident)
        if not conf:
            continue
        ag = Agent(ident, {**conf, "max_appels": 2, "json_mode": conf.get("json_mode", False)})
        if not ag.cle:
            continue
        rep = ag.demander(
            "Tu identifies des produits. Réponds en json uniquement.",
            "Pour chaque ligne « id | titre d'annonce », donne le nom exact du produit : marque + modèle + "
            "capacité, taille, couleur et version si elles identifient la variante exacte. "
            "Conserve la référence fabricant, sans texte promo ni nom de magasin. "
            "Si ce n'est pas un produit physique précis (lot, code promo, abonnement, sélection), mets null.\n"
            'Format json : {"produits": [{"id": "...", "nom": "..." }]}\n\n' + lignes)
        d = extraire_json(rep) if rep else None
        if agent is None or (d and d.get("produits")):
            agent = ag
        if d and d.get("produits"):
            break
    for x in (d or {}).get("produits", []):
        if isinstance(x, dict) and x.get("id") and x.get("nom"):
            noms[str(x["id"])] = str(x["nom"])[:60]
    return noms, agent


def meme_produit(titre_annonce, titre_comparateur):
    """Contrôle par l'IA (Gemini) : l'offre et le prix de référence parlent-ils du MÊME produit exact ?
    Évite les fausses affaires (ex. SSD 1 To comparé à un 4 To). True / False / None (IA indisponible)."""
    if not titre_comparateur:
        return None
    from .ia import gemini_oui_non
    return gemini_oui_non("Ces deux titres désignent-ils exactement le même produit neuf (même marque, même modèle, "
                          "même capacité/taille, même version ; la couleur peut différer) ?\n"
                          f"A : {titre_annonce}\nB : {titre_comparateur}")


def examiner(a, nom, maintenant, regles, deja):
    """Examine UNE offre. Renvoie l'alerte (dict) ou None. Une erreur ici n'arrête jamais le tour."""
    signal = bool(SIGNAUX.search(a["titre"] + " " + (a.get("description") or "")))
    pp = sante.protege("comparateur", comparateurs.prix_plancher, nom) if nom else None
    # Une référence exacte existe déjà : ne pas perdre l'offre si le comparateur
    # ne répond pas, ni comparer une occasion au seul prix barré historique.
    from . import keepa
    k = None
    if a.get("asin") and (not pp or str(a.get("source", "")).startswith("keepa-")):
        k = sante.protege("keepa_asin", keepa.fiche, asin=a["asin"], pays="FR")
        if k and not k.get("erreur") and k.get("prix_neuf"):
            p = k["prix_neuf"]
            if not pp or not pp.get("prix_min") or p < pp["prix_min"]:
                pp = {"prix_min": p, "ou": "keepa/amazon.fr", "lien": k.get("lien")}
    if not (pp or {}).get("prix_min") and not signal:
        a["_a_reessayer"] = True
        return None
    pmin = (pp or {}).get("prix_min")
    if pmin:
        base.noter_prix(nom, pmin, pays="FR", site=(pp or {}).get("ou", ""), lien=(pp or {}).get("lien", ""), source="comparateur", denicheur="A")
    if a.get("prix") and a.get("devise", "EUR") and nom:
        base.noter_prix(nom, a["prix"], pays=a.get("pays", ""), site=a.get("marchand") or "", lien=a.get("lien") or "",
                        devise=a.get("devise") or "EUR", source=a.get("source", ""), denicheur="A")
    cout = equipe.cout_achat(a, regles)
    ecart = round(a["prix"] / pmin, 3) if pmin else None
    if a["id"] in deja:
        return None
    if demande.au_dessus_du_prix_max(a["titre"], a.get("prix"), DEMANDE):
        return None  # cible de David avec prix d'achat maximum : plus cher que ce maximum, pas d'alerte
    if not ((ecart is not None and ecart <= SEUIL_ECART and pmin >= 30) or (signal and (ecart is None or ecart <= 0.85))):
        return None
    x = {**{k: a.get(k) for k in ("id", "titre", "prix", "devise", "marchand", "lien", "pays", "source", "temperature", "categorie", "prix_verifie", "prix_page", "prix_carte", "preuve_prix", "preuve_livraison", "livraison_fr_confirmee", "cout_total_confirme", "lien_marchand")},
         "nom_produit": nom, "cout_achat": cout, "prix_plancher": pp, "ecart_vs_neuf_min": ecart,
         "economie_pct": round((1 - ecart) * 100) if ecart else None,
         "type": "bon_plan", "signal_erreur_prix": signal, "trouve_le": maintenant.isoformat(timespec="minutes"),
         "statut": "a_verifier"}
    # même produit ? (contrôle IA du prix de référence)
    ref = ((((pp or {}).get("sources") or {}).get("achatmoinscher") or {}).get("meilleur") or {}).get("titre")
    mp = sante.protege("ia_meme_produit", meme_produit, a["titre"], ref)
    x["meme_produit_ia"] = mp
    if mp is False and not signal:
        return None  # le prix de référence concerne un autre produit : fausse affaire écartée
    # contre-vérification automatique sur idealo (Apify) + prix réels Vinted / Leboncoin
    pi = sante.protege("apify_idealo", apify.prix_idealo, nom) if nom else None
    if pi:
        x["idealo"] = pi
        x["ecart_vs_idealo"] = round(a["prix"] / pi["prix_min"], 3)
        base.noter_prix(nom, pi["prix_min"], pays="FR", site="idealo", lien=pi.get("lien", ""), source="apify:idealo", denicheur="A")
        if x["ecart_vs_idealo"] > 0.85 and not signal:
            return None  # idealo montre que ce n'est pas une vraie affaire : on n'alerte pas
        x["prix_plancher"] = {"prix_min": min(pi["prix_min"], pmin or 1e9), "ou": "idealo", "lien": pi["lien"]}
    if nom:
        x["revente_reelle"] = sante.protege("apify_revente", apify.revente_reelle, nom, a["prix"])
        # fiche Amazon par Keepa (10 jetons, abonnement) : ASIN, EAN, prix neuf/occasion Amazon, vendeurs, ventes 30 j
        from . import keepa
        k = k or (sante.protege("keepa_asin", keepa.fiche, asin=a["asin"], pays="FR") if a.get("asin")
                  else sante.protege("keepa_recherche", keepa.rechercher, nom, "FR", a["prix"]))
        if k and not k.get("erreur") and not public_different(a["titre"], k.get("titre")):
            x["keepa"] = k
            x["asin"], x["ean"] = k.get("asin"), k.get("ean")
            x["vendeurs_amazon"], x["ventes_estimees_30j"] = k.get("nb_vendeurs_neuf"), k.get("ventes_estimees_30j")
            if k.get("prix_neuf"):
                pp2 = x.get("prix_plancher") or {}
                if not pp2.get("prix_min") or k["prix_neuf"] < pp2["prix_min"]:
                    x["prix_plancher"] = {"prix_min": k["prix_neuf"], "ou": "keepa/amazon.fr", "lien": k.get("lien")}
                    x["ecart_vs_neuf_min"] = round(a["prix"] / k["prix_neuf"], 3)
                    x["economie_pct"] = round((1 - x["ecart_vs_neuf_min"]) * 100)
                base.noter_prix(nom, k["prix_neuf"], pays="FR", site="amazon.fr", lien=k.get("lien", ""), source="keepa", denicheur="A")
    dm = demande.est_demande(a["titre"], DEMANDE)
    if dm:
        x["demande_forte"] = dm
    x["canaux"] = sante.protege("canaux", equipe.canaux_de_vente, x, regles, defaut=[])
    # lecture de la page du bon plan et du marchand (prix, expirée ?, livraison France, code) : Claude n'a plus à l'ouvrir
    x["page_offre"] = sante.protege("lecture_page", lecteur.lire_offre, x)
    if x["page_offre"] and x["page_offre"].get("expiree") and not signal:
        return None  # déjà expirée : pas d'alerte
    x["denicheur"] = "A"
    return x


def tour():
    maintenant = datetime.now(timezone.utc)
    debut = time.monotonic()
    sources = [s for s in _lire("config/sources.json", {})["sources"] if s.get("actif", True)]
    regles = _lire("config/regles.json", {})
    DEMANDE.update(sante.protege("demande_B", demande.tendances, defaut={}) or {})
    annonces, etat = sante.protege("collecte", collecte.collecter, sources, defaut=([], {}))
    annonces = list({a["id"]: a for a in annonces + annonces_keepa()}.values())
    for a in annonces:
        identifier_asin(a)
    # Nouveau format : les anciens identifiants seuls n'attestent ni le prix ni
    # une vérification réussie. Migration progressive, toujours limitée à 25/tour.
    vus = _lire("data/etat/vus_veille_v2.json", {})
    nouvelles = [a for a in annonces if a_revoir(a, vus, maintenant)]
    candidates = equipe.prefiltre(nouvelles, regles)
    candidates.sort(key=priorite, reverse=True)
    lot = candidates[:MAXI_PRODUITS]
    sans_identite = [a for a in lot if not a.get("asin")]
    noms, agent = (sante.protege("ia_noms", nommer, sans_identite, defaut=({}, None)) if sans_identite else ({}, None))
    noms.update({a["id"]: a["titre"] for a in lot if a.get("asin")})
    alertes = _lire("data/alertes.json", [])
    deja = {x["id"] for x in alertes}
    nouvelles_alertes = []
    examinees = 0
    for a in lot:
        if time.monotonic() - debut > BUDGET_EXAMEN_S:
            sante.noter("erreur", "budget temps", f"tour arrêté après {examinees} produits sur {len(lot)} ({int(time.monotonic() - debut)} s) : le reste sera revu au prochain tour")
            break
        examinees += 1
        try:
            x = examiner(a, noms.get(a["id"]), maintenant, regles, deja)
            if x:
                nouvelles_alertes.append(x)
                deja.add(x["id"])
                _ecrire("data/alertes.json", (alertes + nouvelles_alertes)[-500:])  # écrit tout de suite : une coupure ne perd rien
        except Exception as e:
            a["_a_reessayer"] = True
            sante.noter("erreur", "examen offre", f"{a.get('titre', '')[:60]} : {type(e).__name__}: {e}")
    lot = lot[:examinees]
    # relecture des pages des alertes encore à vérifier (expirée ? prix remonté ?), 4 au plus par tour, si le temps le permet
    if time.monotonic() - debut < BUDGET_TOUR_S - 90:
        n_relues = sante.protege("relecture_pages", lecteur.relire, alertes, maxi=4, defaut=0) or 0
        if n_relues:
            _ecrire("data/alertes.json", (alertes + nouvelles_alertes)[-500:])
    # chasse ciblée quotidienne sur les produits les plus demandés (occasion neuve sous-cotée)
    for t in (sante.protege("chasse_C", demande.chasse_ciblee, regles, defaut=[]) or []):
        try:
            ident = "chasse-" + t["recherche"][:30].replace(" ", "-") + "-" + t["canal"]
            if ident not in deja:
                nouvelles_alertes.append({"id": ident, "titre": f'{t["recherche"]} : annonce {t["canal"]} à {t["annonce_min"]} € (idealo {t["idealo"]["prix_min"]} €)',
                                          "prix": t["annonce_min"], "devise": "EUR", "marchand": t["canal"], "lien": t.get("lien"),
                                          "denicheur": t.get("par", "C"),
                                          "pays": "FR", "source": "chasse_ciblee", "nom_produit": t["recherche"],
                                          "cout_achat": t["annonce_min"] + 5, "idealo": t["idealo"], "demande_forte": t,
                                          "trouve_le": maintenant.isoformat(timespec="minutes"), "statut": "a_verifier"})
        except Exception as e:
            sante.noter("erreur", "alerte C", f"{type(e).__name__}: {e}")
    # ne marquer « vu » que ce qui a été examiné (le reste sera revu au prochain tour)
    ids_lot = {a["id"] for a in lot}
    ids_candidates = {a["id"] for a in candidates}
    for a in nouvelles:
        if a["id"] not in ids_candidates or a["id"] in ids_lot:
            delai = timedelta(hours=1 if a.get("_a_reessayer") else 24)
            vus[a["id"]] = {"empreinte": empreinte(a), "prochain": (maintenant + delai).isoformat()}
    vus = dict(sorted(vus.items(), key=lambda x: x[1].get("prochain", ""))[-20000:])
    _ecrire("data/etat/vus_veille_v2.json", vus)
    if nouvelles_alertes:
        _ecrire("data/alertes.json", (alertes + nouvelles_alertes)[-500:])
        from . import telegram, fiche
        a_envoyer = [x for x in nouvelles_alertes if x.get("type") == "bon_plan" and (x.get("economie_pct") or 0) >= 15]
        promet = [x for x in a_envoyer if fiche.evaluer(x, {})["feu"] != "rouge"]
        from . import ebay  # gratuit : prix d'occasion et annonces neuves sur eBay pour les annonces prometteuses
        sante.protege("ebay alertes", ebay.controler, [x for x in promet if not x.get("ebay")], maxi=10)
        vol = sante.protege("volumes alertes", fiche.completer_volumes, promet, defaut=None)
        from . import verif_prix
        for x in a_envoyer:  # fiche de décision complète au fil de l'eau (rouge = rien envoyé)
            if fiche.evaluer(x, vol or {})["feu"] == "rouge":
                continue
            # contrôle du prix sur la fiche du produit AVANT d'alerter (incident Makita LS1019L du 05/11)
            v = sante.protege("contrôle prix", verif_prix.controler, x, defaut={"statut": "inconnu", "prix_page": None}) or {}
            x["controle_prix"] = v
            if v.get("statut") == "different" and v.get("prix_page"):
                delta = v["prix_page"] - x["prix"]
                x["prix_annonce_initial"], x["prix"] = x["prix"], v["prix_page"]
                # Le nouveau prix correspond maintenant au contrôle reçu.
                x["controle_prix"] = {**v, "statut": "ok"}
                if x.get("cout_achat"):
                    x["cout_achat"] = round(x["cout_achat"] + delta, 2)
                for c in x.get("canaux") or []:
                    if isinstance(c, dict) and isinstance(c.get("marge_nette"), (int, float)):
                        c["marge_nette"] = round(c["marge_nette"] - delta, 2)
            elif v.get("statut") != "ok" and str(x.get("source", "")).startswith("pc:"):
                continue  # prix lu sur une page par le PC et non confirmé par la fiche produit : pas d'alerte
            from .logistique import appliquer
            appliquer(x, v.get('preuve_livraison'))
            x['canaux'] = equipe.canaux_de_vente(x, regles) or []
            # MÊME PRODUIT ? (piège du 05/11 : lot de 2 roues comparé à un lot de 8) -> sinon pas d'alerte
            if x.get("prix_plancher"):
                from . import meme_produit
                mp = sante.protege("même produit", meme_produit.controler_alerte, x, defaut={"meme": None, "raison": "erreur"}) or {}
                x["meme_produit"] = mp
                if mp.get("meme") is False:
                    print(f"  écartée (pas le même produit) : {str(x.get('titre'))[:60]} <> {str(mp.get('reference'))[:60]} — {mp.get('raison')}")
                    continue
            if True:
                if (x.get("economie_pct") or 0) >= 60 or x.get("signal_erreur_prix"):
                    x["erreur_prix_probable"] = True  # sous 40 % du neuf : erreur de prix probable -> commander vite, 1 unité, attendre l'expédition
                sante.protege("telegram alerte", telegram.alerte, x, vol)
        _ecrire("data/alertes.json", (alertes + nouvelles_alertes)[-500:])  # garde la fiche (feu) de chaque alerte
    # annonces de particuliers trouvées par le Chasseur PC (data/pc/chasse.json) : alerte Telegram une seule fois chacune
    from . import telegram as _tg
    chasse = _lire("data/pc/chasse.json", {}).get("annonces", [])
    deja_c = set(_lire("data/etat/chasse_alertees.json", []))
    nouvelles_c = [x for x in chasse if x["id"] not in deja_c and "sous-coté" in (x.get("signaux") or []) and (x.get("ecart_pct") or 0) >= 35]
    for x in nouvelles_c[:10]:
        sante.protege("telegram chasseur", _tg.envoyer, f"🟠 <b>Chasseur</b> — {x['titre']}\n{x['site']} : <b>{x['prix']} €</b> (référence occasion {x.get('reference')} €, -{x.get('ecart_pct')} %) · {', '.join(x.get('signaux') or [])}\nproduit cherché : {x.get('produit')} ({x.get('origine')})\n{x['lien']}")
        deja_c.add(x["id"])
    if nouvelles_c:
        _ecrire("data/etat/chasse_alertees.json", sorted(deja_c)[-3000:])
    # classements du jour USA / Japon / Royaume-Uni / Chine, photographiés à 23 h 59 heure locale (fenêtre 23 h 40 - 1 h)
    from . import classements
    sante.protege("classements", classements.tour)
    bilan = {"heure": maintenant.astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M"),
             "duree_s": int(time.monotonic() - debut),
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
    # mémoire des annonces vues par A (3 jours) pour le dénicheur C
    limite = (maintenant - timedelta(days=3)).isoformat(timespec="minutes")
    recentes = [r for r in _lire("data/etat/annonces_recentes.json", []) if r.get("t", "") >= limite]
    recentes += [{"titre": a["titre"][:100], "prix": a.get("prix"), "devise": a.get("devise"), "lien": a.get("lien"), "marchand": a.get("marchand"),
                  "source": a.get("source"), "t": maintenant.isoformat(timespec="minutes")} for a in nouvelles if a.get("prix")]
    _ecrire("data/etat/annonces_recentes.json", recentes[-1500:])
    # journal des recherches gratuites de A : une ligne par source et par catégorie
    par_source = {}
    for a in nouvelles:
        k = (a.get("source") or "?", (a.get("categorie") or "?")[:60])
        par_source[k] = par_source.get(k, 0) + 1
    al_cat = {}
    for x in nouvelles_alertes:
        k = (x.get("source") or "?", (x.get("categorie") or "?")[:60])
        al_cat[k] = al_cat.get(k, 0) + 1
    for (src, cat), n in par_source.items():
        journal.noter("A", "flux:" + src, "", 0.0, n, al_cat.get((src, cat), 0), categorie=cat)
    sante.protege("base", base.sauver)
    jv = _lire("data/veille_journal.json", [])
    _ecrire("data/veille_journal.json", (jv + [bilan])[-200:])
    if not annonces or len(bilan["sources_ko"]) > len(sources) // 2:
        sante.noter("erreur", "sources", f"{len(bilan['sources_ko'])} sources sur {len(sources)} illisibles, {len(annonces)} annonces lues")
    sante.tour_ok({k: bilan[k] for k in ("heure", "annonces", "nouvelles", "examinees", "alertes")})
    print(json.dumps(bilan, ensure_ascii=False))
    for x in nouvelles_alertes:
        try:
            print("ALERTE", str(x.get("titre", ""))[:80], x.get("prix"), "neuf min", (x.get("prix_plancher") or {}).get("prix_min"))
        except Exception:
            pass


if __name__ == "__main__":
    tour()
