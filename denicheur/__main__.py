"""Lancement : python -m denicheur --passage asie|europe [--test]

--test : aucune connexion, aucune IA appelée (données d'exemple) -> gratuit, pour vérifier le code.
"""
import argparse
import re
import json
import os
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import championnat, collecte, ebay, equipe, rapport, verif
from .ia import Agent

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def charger(rel):
    with open(os.path.join(RACINE, rel), encoding="utf-8") as f:
        return json.load(f)


def ecrire(rel, contenu):
    chemin = os.path.join(RACINE, rel)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        if isinstance(contenu, str):
            f.write(contenu)
        else:
            json.dump(contenu, f, ensure_ascii=False, indent=1)


# ---------- mode test (gratuit, hors ligne) ----------
EXEMPLES = [
    ("Lames robot tondeuse Dreame A1 x36", 9.99, "AliExpress", "Jardin", 150),
    ("Étui de transport Insta360 X6", 6.50, "AliExpress", "High-tech", 80),
    ("Protection écran verre trempé Thermomix TM7 (x2)", 3.99, "Amazon", "Maison", 210),
    ("Forfait mobile 100 Go à 9,99€/mois", 9.99, "Free", "Forfaits", 400),
    ("Cocotte fonte émaillée 24 cm", 39.90, "Cdiscount", "Cuisine", 300),
    ("Écouteurs sans fil marque X", 14.99, "Amazon", "High-tech", 500),
]


def lecteur_test(source):
    if source["id"] != "dealabs-tendance":
        return [], None
    out = []
    for i, (t, p, m, c, temp) in enumerate(EXEMPLES):
        out.append({"id": f"test{i}", "titre": t, "temperature": temp, "categorie": c, "marchand": m, "prix": p,
                    "devise": "EUR", "lien": f"https://exemple.test/{i}", "date": "", "source": source["id"],
                    "pays": "FR", "description": ""})
    return out, None


class FauxAgent:
    def __init__(self, ident, conf):
        self.id, self.conf, self.nom = ident, conf, conf["nom"]
        self.appels, self.reussites, self.erreurs, self.duree = 0, 0, [], 0.0
        self.alea = random.Random(ident)

    def disponible(self):
        return self.appels < self.conf.get("max_appels", 5)

    def demander(self, systeme, message):
        self.appels += 1
        if self.conf.get("panne_test"):
            self.erreurs.append("panne simulée")
            return None
        self.reussites += 1
        ids = [l.split(" | ")[0] for l in message.splitlines() if " | " in l]
        if '{"garder"' in systeme:
            return json.dumps({"garder": ids})
        choix = [{"id": i, "domaine": "tech", "plateforme_revente": "amazon", "etat_revente": "neuf",
                  "prix_revente_estime": self.alea.choice([15, 25, 35, 60]), "demande": 4, "concurrence": 2,
                  "mode": "stock", "confiance": 0.7, "erreur_prix": False, "raison": "test"}
                 for i in ids if self.alea.random() < 0.6]
        return "```json\n" + json.dumps({"choix": choix}) + "\n```"


# ---------- passage ----------
# familles d'IA par passage : une famille par rendez-vous, aucune ne s'épuise (Groq : 200 000 jetons/jour)
ANALYSTES_PAR_PASSAGE = {"nuit": ["nemotron", "gptoss", "qwen"], "midi": ["nemotron", "nemotron_nv", "gemma"], "soir": ["nemotron_nv", "gemma", "deepseek"]}


def passage(nom, test=False):
    if nom in ("europe", "asie"):
        nom = "nuit"
    maintenant = datetime.now(timezone.utc)
    import time as _time
    _t0 = _time.time()

    def etape(nom_etape):
        print(f"[{int(_time.time() - _t0):4d} s] {nom_etape}", flush=True)
    paris = maintenant.astimezone(ZoneInfo("Europe/Paris"))
    horodatage = paris.strftime("%Y-%m-%d_%H%M")
    regles, conf_eq = charger("config/regles.json"), charger("config/equipe.json")
    if nom in ANALYSTES_PAR_PASSAGE:
        conf_eq["analystes"] = [a for a in ANALYSTES_PAR_PASSAGE[nom] if a in conf_eq["agents"]]
    with open(os.path.join(RACINE, "skills/methode.md"), encoding="utf-8") as f:
        methode = f.read()
    sources = charger("config/sources.json")["sources"]

    etape("collecte des sources")
    annonces, etat_sources = collecte.collecter(sources, lecteur_test if test else collecte.lire_source)
    if not test:  # + les baisses de prix Amazon.fr du radar Keepa (moissonneur), en amont de Dealabs
        from . import moisson, sante
        radar = sante.protege("radar amazon", moisson.annonces_radar, defaut=[])
        annonces += radar
        etat_sources["keepa-radar"] = {"ok": True, "nb": len(radar), "erreur": None}
        from . import arbitrage as _arb
        arb = sante.protege("arbitrage europe", _arb.annonces_arbitrage, defaut=[])
        annonces += arb
        etat_sources["keepa-arbitrage"] = {"ok": True, "nb": len(arb), "erreur": None}
        from . import demande as _dem
        _nv, _et = sante.protege("hype flux", _dem.hype_flux, defaut=([], {}))
        for k, v in (_et or {}).items():
            etat_sources["hype:" + k] = v

    # ne réanalyser que les nouveautés
    chemin_vus = "data/etat/vus.json" if not test else "data/test/vus.json"
    try:
        vus = charger(chemin_vus)
    except (OSError, json.JSONDecodeError):
        vus = []
    deja = set(vus)
    nouvelles = [a for a in annonces if a["id"] not in deja]

    prefiltrees = equipe.prefiltre(nouvelles, regles)
    Classe = FauxAgent if test else Agent
    agents = {k: Classe(k, v) for k, v in conf_eq["agents"].items()}

    trieur = agents.get(conf_eq.get("trieur") or "")
    if conf_eq.get("trieur"):
        tries, tri_ok = equipe.trier(trieur, prefiltrees, regles["taille_lot"]) if prefiltrees else ([], True)
    else:  # pas d'IA pour le tri : le filtre du programme suffit (plus fiable)
        tries, tri_ok = prefiltrees, True
    capacite = min(agents[a].conf.get("taille_lot", regles["taille_lot"]) * agents[a].conf.get("max_appels", 5)
                   for a in conf_eq["analystes"])
    tries = tries[:capacite]  # les plus populaires d'abord (déjà triés par température)

    tous_choix, remplacements = [], {}
    etape(f"tribunal : {len(tries)} annonces, analystes {conf_eq['analystes']}")
    for nom_a in conf_eq["analystes"]:
        tous_choix += equipe.analyser(agents[nom_a], tries, methode, regles["taille_lot"])
        if tries and agents[nom_a].reussites == 0:
            liste = conf_eq.get("remplacants", {}).get(nom_a) or []
            liste = [liste] if isinstance(liste, str) else liste
            for remp in liste:  # le premier remplaçant libre joue à sa place, avec les mêmes bons plans
                if remp in agents and remp not in remplacements and remp not in conf_eq["analystes"]:
                    remplacements[remp] = nom_a
                    tous_choix += equipe.analyser(agents[remp], tries, methode, regles["taille_lot"])
                    if agents[remp].reussites:
                        break

    retenus, candidats = equipe.consolider(tries, tous_choix, regles)
    # SCORE MÉCANIQUE : les annonces venues de Keepa (radar, arbitrage) ont déjà un prix de référence France
    # (ref_fr), des ventes et des vendeurs : on les retient par calcul, sans attendre le tribunal.
    deja_m = {c["id"] for c in retenus}
    for a in nouvelles if not test else []:
        if a["id"] in deja_m or not str(a.get("source", "")).startswith("keepa") or not a.get("ref_fr") or not a.get("prix"):
            continue
        cout = equipe.cout_achat(a, regles)
        prix_rev = round(a["ref_fr"] * regles["profils_acheteurs"]["petit_budget"]["prix_vs_neuf_min"], 2)
        marge = equipe.marge_nette(prix_rev, "leboncoin", cout, regles)
        if marge < regles["seuils"]["marge_nette_min"] or (a.get("vendeurs") or 0) > 9:
            continue
        retenus.append({**{k: a.get(k) for k in ("id", "titre", "prix", "devise", "marchand", "lien", "pays", "source", "temperature")},
                        "domaine": "autre", "nom_produit": (a["titre"].split(" [")[0])[:70], "plateforme_revente": "leboncoin",
                        "prix_revente_estime": prix_rev, "cout_achat": cout, "marge_nette": marge,
                        "rentabilite": round(marge / cout, 3) if cout else 0, "demande": 3, "concurrence": 3, "consensus": 1,
                        "agents": ["calcul"], "mode": "stock", "erreur_prix": False, "raisons": {"calcul": a.get("description", "")[:160]},
                        "score": round(marge / cout * 100, 1) if cout else 0, "asin": a.get("asin"), "ean": a.get("ean"),
                        "vendeurs_amazon": a.get("vendeurs"), "ventes_estimees_30j": a.get("ventes_30j")})
        deja_m.add(a["id"])
    retenus.sort(key=lambda c: c["score"], reverse=True)
    etape(f"consolidation : {len(retenus)} retenus")
    # + les bons plans trouvés par la VEILLE (Idéfix) depuis 24 h : ils passent la même vérification complète que les autres
    if not test:
        from datetime import timedelta
        limite = (maintenant - timedelta(hours=24)).isoformat(timespec="minutes")
        deja_ids = {c["id"] for c in retenus}
        try:
            alertes = charger("data/alertes.json")
        except (OSError, json.JSONDecodeError):
            alertes = []
        for x in alertes:
            if x.get("type") != "bon_plan" or (x.get("trouve_le") or "") < limite or x["id"] in deja_ids or x.get("statut") == "rejete":
                continue
            if equipe.EXCLUS.search(x.get("titre") or "") or equipe.EXCLUS.search(x.get("marchand") or ""):
                continue  # dématérialisé, abonnement… : jamais revendable
            canaux = [k for k in (x.get("canaux") or []) if isinstance(k, dict)]
            meilleur = max(canaux, key=lambda k: k.get("marge_nette") or 0, default=None)
            if not meilleur:
                continue
            cout = x.get("cout_achat") or equipe.cout_achat(x, regles)
            retenus.append({**{k: x.get(k) for k in ("id", "titre", "prix", "devise", "marchand", "lien", "pays", "source", "temperature")},
                            "domaine": "autre", "nom_produit": x.get("nom_produit") or x["titre"], "plateforme_revente": meilleur["canal"],
                            "prix_revente_estime": meilleur["prix_vente"], "cout_achat": cout, "marge_nette": meilleur["marge_nette"],
                            "rentabilite": meilleur.get("rentabilite", 0), "demande": 3, "concurrence": 3, "consensus": 1, "agents": ["veille"],
                            "mode": "stock", "erreur_prix": bool(x.get("signal_erreur_prix")), "raisons": {"veille": f"économie {x.get('economie_pct')} % vs neuf le moins cher"},
                            "score": round((x.get("economie_pct") or 0) * 1.5, 1), "veille": True, "idealo": x.get("idealo"),
                            "prix_plancher": x.get("prix_plancher"), "keepa": x.get("keepa"), "ean": x.get("ean"), "asin": x.get("asin"),
                            "vendeurs_amazon": x.get("vendeurs_amazon"), "ventes_estimees_30j": x.get("ventes_estimees_30j")})
            deja_ids.add(x["id"])
        retenus.sort(key=lambda c: c["score"], reverse=True)

    # vérification des prix sur Google (Gemini + recherche), puis marge recalculée au prix prudent
    if test:
        bilan_verif = {"faits": 0, "erreurs": ["mode test"]}
    else:
        conf_v = conf_eq["agents"][conf_eq.get("verificateur", "gemini")]
        modeles_v = [conf_v["modele"]] + list(conf_v.get("modeles_secours", []))[:2]
        etape("vérification Gemini")
        bilan_verif = verif.verifier_prix(retenus, cle=os.environ.get(conf_v["cle_env"], "").strip(), modeles=modeles_v, maxi=20)
    # prix réels des annonces eBay (API officielle, gratuite) : tous les passages
    etape("prix eBay")
    bilan_ebay = {"faits": 0, "erreurs": ["mode test"]} if test else ebay.controler(retenus)
    # prix plancher automatique (prix neuf le plus bas en France, produit exact) :
    # 1) comparateurs gratuits ; 2) idealo via le robot Apify pour les meilleures affaires (budget plafonné).
    # NB : la variable s'appelle nom_p, pas nom : « nom » est le nom du passage (europe/asie) et ne doit pas être écrasé.
    if not test:
        from . import apify, comparateurs, keepa
        etape("identification Keepa")
        # 0) IDENTIFICATION D'ABORD (Keepa, 10 jetons par produit, compris dans l'abonnement) : ASIN + EAN + prix Amazon
        #    + nombre de vendeurs + ventes 30 j. Le radar Amazon connaît déjà son ASIN (id = keepa-<ASIN>-<type>).
        for c in retenus[:40]:
            if c.get("keepa") and not c["keepa"].get("erreur"):
                continue
            try:
                if str(c.get("id", "")).startswith("keepa-"):
                    asin = c["id"].split("-")[1]
                    k = keepa.fiche(asin=asin, pays="FR")
                else:
                    k = keepa.rechercher(c.get("nom_produit") or c["titre"], "FR", prix_attendu=c.get("prix"))
            except Exception as e:
                k = {"erreur": type(e).__name__}
            if k and not k.get("erreur"):
                if k.get("prix_neuf") and k.get("moyenne_90j") and k["prix_neuf"] > k["moyenne_90j"] * 1.25:
                    k["prix_neuf_vendeur_tiers"], k["prix_neuf"] = k["prix_neuf"], k.get("plus_bas_90j") or k["moyenne_90j"]
                c["keepa"] = k
                c["asin"] = k.get("asin")
                if k.get("ean"):
                    c["ean"] = str(k["ean"])
                if k.get("nb_vendeurs_neuf") is not None:
                    c["vendeurs_amazon"] = k["nb_vendeurs_neuf"]
                if k.get("ventes_estimees_30j") is not None:
                    c["ventes_estimees_30j"] = k["ventes_estimees_30j"]
                if k.get("prix_neuf"):
                    pp = c.setdefault("prix_plancher", {"nom": c.get("nom_produit"), "sources": {}})
                    if not pp.get("prix_min") or k["prix_neuf"] < pp["prix_min"]:
                        pp["prix_min"], pp["ou"], pp["lien"] = k["prix_neuf"], "keepa/amazon.fr", k.get("lien")
                    if k.get("moyenne_90j"):
                        c["remise_sincere"] = round(c["prix"] / k["moyenne_90j"], 3) <= 0.95
            elif k and k.get("erreur"):
                c["keepa_erreur"] = k["erreur"]
        nb_idealo = int(regles.get("idealo_passage_max", 10))
        etape("comparateurs + idealo")
        for i, c in enumerate(retenus[:25]):
            nom_p = c.get("nom_produit")
            if not nom_p:
                continue
            avant = c.get("prix_plancher") or {}
            try:
                c["prix_plancher"] = comparateurs.prix_plancher(nom_p)
            except Exception as e:
                c["prix_plancher"] = {"erreur": type(e).__name__}
            if avant.get("prix_min") and (not c["prix_plancher"].get("prix_min") or avant["prix_min"] < c["prix_plancher"]["prix_min"]):
                c["prix_plancher"].update({"prix_min": avant["prix_min"], "ou": avant.get("ou"), "lien": avant.get("lien")})
            if c.get("idealo") and c["idealo"].get("prix_min"):
                pi = c["idealo"]
                pp = c["prix_plancher"]
                if not pp.get("prix_min") or pi["prix_min"] < pp["prix_min"]:
                    pp["prix_min"], pp["ou"], pp["lien"] = pi["prix_min"], "idealo", pi.get("lien")
                if pi.get("gtin") and not c.get("ean"):
                    c["ean"] = str(pi["gtin"])
            elif i < nb_idealo:
                try:
                    pi = apify.prix_idealo(nom_p)
                except Exception as e:
                    pi = None
                    c["idealo_erreur"] = type(e).__name__
                if pi:
                    c["idealo"] = pi
                    pp = c["prix_plancher"]
                    if not pp.get("prix_min") or pi["prix_min"] < pp["prix_min"]:
                        pp["prix_min"], pp["ou"], pp["lien"] = pi["prix_min"], "idealo", pi.get("lien")
                    if pi.get("gtin"):
                        c["ean"] = str(pi["gtin"])
        # 3) Keepa (Amazon.fr) par code EAN : prix neuf, moyenne 90 jours, remise sincère, compteur de ventes
        for c in retenus[:25]:
            if not c.get("ean") or c.get("keepa"):
                continue
            try:
                k = keepa.fiche(ean=c["ean"], pays="FR")
            except Exception as e:
                k = {"erreur": type(e).__name__}
            if not k:
                continue
            c["keepa"] = k
            if k.get("prix_neuf"):
                pp = c.setdefault("prix_plancher", {"nom": c.get("nom_produit"), "sources": {}})
                if not pp.get("prix_min") or k["prix_neuf"] < pp["prix_min"]:
                    pp["prix_min"], pp["ou"], pp["lien"] = k["prix_neuf"], "keepa/amazon.fr", k.get("lien")
                if k.get("moyenne_90j"):
                    c["remise_sincere"] = round(c["prix"] / k["moyenne_90j"], 3) <= 0.95
            if k.get("ventes_estimees_30j") is not None:
                c["ventes_estimees_30j"] = k["ventes_estimees_30j"]
        # 4) DataForSEO : volume de recherche Google France des produits retenus (un seul appel, ~0,09 $)
        from . import bingo as _bingo, dataforseo
        # mots-clés tels que les gens les tapent (Gemini, cache) : un titre long n'a aucun volume Google
        noms = [c["nom_produit"] for c in retenus[:40] if c.get("nom_produit")]
        cache_mc = _bingo.mots_cles_ia(noms, maxi_appels=3) if noms else {}
        for c in retenus[:40]:
            if c.get("nom_produit"):
                c["mot_cle"] = cache_mc.get(c["nom_produit"]) or _bingo.mot_cle(c["nom_produit"])
        mots = list(dict.fromkeys(c["mot_cle"] for c in retenus[:40] if c.get("mot_cle")))
        try:
            vols = dataforseo.volumes(mots, "FR") if mots else {}
        except Exception as e:
            vols = {"_erreur": type(e).__name__}
        for c in retenus[:40]:
            v = vols.get((c.get("mot_cle") or "").lower()) or vols.get(c.get("mot_cle") or "")
            if v and v.get("volume_mensuel"):
                c["demande_google"] = v
        # concurrence eBay.fr : nombre d'annonces neuves (déjà relevées par le contrôle eBay)
        for c in retenus[:40]:
            neuf = (c.get("ebay") or {}).get("neuf")
            if isinstance(neuf, dict) and neuf.get("nb") is not None:
                c["annonces_ebay"] = neuf["nb"]
    s_ = regles["seuils"]
    for c in retenus:
        c["canaux"] = equipe.canaux_de_vente(c, regles)
    for c in retenus:
        v, plaf_ebay = c.get("verification"), ebay.plafond(c)
        pmin = (c.get("prix_plancher") or {}).get("prix_min")
        if not v and plaf_ebay is None and not pmin:
            c["feu"], c["concurrence_amazon"] = "rouge", "inconnue"
            c["marge_verifiee"], c["passe_verif"] = c.get("marge_verifiee", 0), False
            continue
        plafonds = [c["prix_revente_estime"]]
        if pmin:
            plafonds.append(round(pmin * 0.9, 2))  # un acheteur ne paie pas plus que 90 % du neuf le moins cher
        if v:
            plafonds.append(v["prix_revente_prudent"])
        if plaf_ebay is not None:
            plafonds.append(plaf_ebay)
        c["prix_revente_prudent"] = min(plafonds)
        cout = c["cout_achat"]
        c["marge_verifiee"] = equipe.marge_nette(c["prix_revente_prudent"], c["plateforme_revente"], cout, regles)
        c["rentabilite_verifiee"] = round(c["marge_verifiee"] / cout, 3) if cout else 0
        neuf_ebay = ((c.get("ebay") or {}).get("neuf") or {}).get("p25")
        # règle du 04/11 : une marge ≥ 20 € suffit même si elle fait moins de 30 % du coût (objectif : 30 € par vente)
        c["passe_verif"] = (c["marge_verifiee"] >= s_["marge_nette_min"] and (c["rentabilite_verifiee"] >= s_["rentabilite_min"] or c["marge_verifiee"] >= 20)
                            and not (v and v["deja_moins_cher_ailleurs"])
                            and not (neuf_ebay and neuf_ebay <= c["prix"])
                            and not (pmin and c["prix"] >= pmin * 0.92))
        # CARTE TROIS FEUX (règles de David, 04/11) : vert = achète N ; orange = achète 1 pour tester ; rouge = passe.
        vend = c.get("vendeurs_amazon")
        pmin_ok = bool(pmin)
        concurrence = "forte" if (vend or 0) >= 10 else "moyenne" if (vend or 0) >= 5 else "faible" if vend is not None else "inconnue"
        assez_moins_cher = bool(pmin and c["prix"] <= pmin * 0.85)
        # garde-fous avant un vert : marque/demande inconnue (arbitrage sur un produit sans nom, 1 seul vendeur en France,
        # aucune recherche Google) ou achat sur AliExpress/Temu (import, garantie) -> orange au maximum (1 unité pour tester)
        demande_ok = bool((c.get("demande_google") or {}).get("volume_mensuel")) or bool(c.get("bingo")) or (c.get("ventes_estimees_30j") or 0) >= 20
        sans_nom = str(c.get("source", "")).startswith("keepa") and ((c.get("vendeurs_amazon") or 0) <= 1 and not demande_ok)
        import_risque = bool(re.search(r"aliexpress|temu|shein|banggood|wish", (c.get("marchand") or "") + " " + (c.get("lien") or ""), re.I))
        if c["passe_verif"] and pmin_ok and c["marge_verifiee"] >= 20 and concurrence in ("faible", "inconnue") and not sans_nom and not import_risque:
            feu = "vert"
        elif c["passe_verif"] and (concurrence != "forte") and (concurrence != "moyenne" or assez_moins_cher):
            feu = "orange"
        elif c["marge_verifiee"] >= s_["marge_nette_min"] and not pmin_ok:
            feu = "orange"  # marge probable mais prix neuf de référence non prouvé : à vérifier par l'audit
        else:
            feu = "rouge"
        c["feu"], c["concurrence_amazon"] = feu, concurrence
        # fourchette d'occasion réellement constatée (Gemini/Google, eBay, Amazon Seconde main)
        occ = [x for x in ((v or {}).get("occasion_bas"), (v or {}).get("occasion_haut"),
                           ((c.get("ebay") or {}).get("occasion") or {}).get("p25"), ((c.get("ebay") or {}).get("occasion") or {}).get("mediane"),
                           (c.get("keepa") or {}).get("occasion")) if isinstance(x, (int, float)) and x > 0]
        if occ:
            c["occasion"] = {"bas": min(occ), "haut": max(occ),
                             "position_neuf": round(c["prix"] / min(occ), 2)}  # < 1 : notre neuf sous l'occasion la moins chère = or
    # SCORE DE VENTE (skills/vente.md) : demande x marge x vitesse / concurrence, bonus hype, malus marque fermée / import
    for c in retenus:
        vol = (c.get("demande_google") or {}).get("volume_mensuel") or 0
        v30 = c.get("ventes_estimees_30j") or 0
        demande = 1 + min(vol, 20000) / 2000 + min(v30, 100) / 20 + (2 if c.get("bingo") else 0)
        marge = max(c.get("marge_verifiee") or 0, 0)
        vend = (c.get("vendeurs_amazon") or 0) + (c.get("annonces_ebay") or 0) / 5
        concurrence = 1 + vend / 3
        vitesse = 1 + (10 if v30 >= 30 else 5 if v30 >= 10 else 1 if v30 >= 3 else 0.3)
        malus = 0.5 if (c.get("concurrence_amazon") == "forte") else 1.0
        malus *= 0.7 if re.search(r"aliexpress|temu|shein", (c.get("marchand") or ""), re.I) else 1.0
        c["score_vente"] = round(demande * marge * vitesse / concurrence * malus, 1)
    retenus.sort(key=lambda c: ({"vert": 3, "orange": 2}.get(c.get("feu"), 0), c.get("score_vente", 0), c["score"]), reverse=True)
    # rapports Demande / Concurrence (gratuits) pour les 10 meilleures affaires
    if not test:
        from . import rapports
        try:
            tok_r = ebay.jeton()
        except Exception:
            tok_r = None
        for c in retenus[:10]:
            q = c.get("nom_produit") or ebay.requete(c["titre"])
            if tok_r:
                try:
                    c["rapport_concurrence"] = rapports.concurrence(tok_r, q, c["prix"])
                except Exception as e:
                    c["rapport_concurrence"] = {"erreur": type(e).__name__}
            c["rapport_demande"] = rapports.demande(q, c.get("temperature"))

    # BINGO (une fois par jour, au passage de la nuit ; les autres passages relisent data/bingo.json)
    if not test:
        from . import bingo, sante
        if nom == "nuit":
            etape("bingo")
            sante.protege("bingo", bingo.jour)
            from . import sourceur
            etape("sourceur")
            sante.protege("sourceur", sourceur.jour, 10)
        for c in retenus:
            c["bingo"] = bingo.est_bingo(c.get("nom_produit") or c["titre"])
    etape("enregistrement")
    base = "data/test" if test else "data"
    championnat.enregistrer(os.path.join(RACINE, base, "championnat"), horodatage, nom, tous_choix)
    championnat.enregistrer_fiabilite(os.path.join(RACINE, base, "championnat"), horodatage,
                                      {k: (a.appels if a.appels < 10**6 else a.reussites + 1, a.reussites)
                                       for k, a in agents.items() if a.appels})
    classement = championnat.classement(os.path.join(RACINE, base, "championnat"), os.path.join(RACINE, base, "audits"))

    resultat = {
        "passage": nom,
        "horodatage": horodatage,
        "date_affichee": paris.strftime("%d/%m/%Y à %H h %M"),
        "statut": "Provisoire : en attente de l’audit de Claude",
        "test": test,
        "sources": etat_sources,
        "nb_annonces": len(annonces),
        "nb_nouvelles": len(nouvelles),
        "nb_prefiltres": len(prefiltrees),
        "nb_tries": len(tries),
        "tri_ok": tri_ok,
        "agents": {k: {"appels": a.appels, "reussites": a.reussites, "erreurs": a.erreurs,
                       "choix": sum(1 for c in tous_choix if c["agent"] == k),
                       **({"remplace": remplacements[k]} if k in remplacements else {})}
                   for k, a in agents.items() if a.appels or k in conf_eq["analystes"]},
        "remplacements": remplacements,
        "candidats": retenus[:40],
        "verification": bilan_verif,
        "verification_ebay": bilan_ebay,
        "ecartes_sous_seuil": len(candidats) - len(retenus),
        "annonces_analysees": tries,
    }
    ecrire(f"{base}/passages/{horodatage}_{nom}.json", resultat)
    ecrire(f"{base}/dernier_passage.json", resultat)
    ecrire(f"{base}/classement.json", classement)
    ecrire(f"{base}/rapport.html", rapport.page(resultat, classement))
    if not test:  # page de David reconstruite, puis Telegram : seulement s'il y a des cartes vertes ou orange (jamais de message vide)
        import importlib.util
        from . import telegram
        try:
            spec = importlib.util.spec_from_file_location("rapport_david", os.path.join(RACINE, "saas/rapport_david.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.construire()
        except Exception as e:
            sante.noter("erreur", "rapport david", f"{type(e).__name__}: {e}")
        if sante.protege("telegram passage", telegram.rapport_passage, resultat):
            sante.protege("telegram fichier", telegram.envoyer_fichier, os.path.join(RACINE, "data/rapport_david.html"),
                          f"Rapport {nom} du {resultat['date_affichee']} (page à onglets, à ouvrir dans le navigateur)")
    # si aucun analyste n'a pu travailler (clés absentes, pannes), on garde les bons plans pour le passage suivant
    if any(a.reussites for k, a in agents.items() if k in conf_eq["analystes"] or k in remplacements):
        ecrire(chemin_vus, (vus + [a["id"] for a in nouvelles])[-5000:])

    print(f"  prix eBay : {bilan_ebay['faits']} produit(s), erreurs {bilan_ebay['erreurs'][:3]}")
    print(f"  vérification Google : {bilan_verif['faits']} produit(s), erreurs {bilan_verif['erreurs'][:3]}")
    print(f"Passage {nom} ({horodatage}) : {len(annonces)} lus, {len(nouvelles)} nouveaux, {len(prefiltrees)} filtrés, "
          f"{len(tries)} triés, {len(retenus)} affaires retenues.")
    for k, v in resultat["agents"].items():
        print(f"  {k}: {v['appels']} appel(s), {v['choix']} choix, erreurs: {v['erreurs'][:2]}")
    for k, v in etat_sources.items():
        print(f"  source {k}: {'OK ' + str(v['nb']) if v['ok'] else 'ERREUR ' + str(v['erreur'])}")
    return resultat


def verifier():
    """Envoie un tout petit message à chaque IA (gratuit) et affiche OK ou l'erreur. N'affiche jamais les clés."""
    import urllib.request
    conf_eq = charger("config/equipe.json")
    lignes = []

    def dire(texte):  # affiche et garde une copie pour le fichier de résultat
        lignes.append(texte)
        print(texte)

    for k, conf in conf_eq["agents"].items():
        a = Agent(k, {**conf, "max_appels": 1})
        rep = a.demander("Tu réponds uniquement en JSON.", 'Réponds avec ce JSON : {"etat": "OK"}')
        if rep is not None:
            dire(f"✅ {conf['nom']} ({conf['cle_env']}) : fonctionne — réponse « {rep.strip()[:30]} »")
            continue
        dire(f"❌ {conf['nom']} ({conf['cle_env']}) : {'; '.join(a.erreurs)[:300]}")
        if a.cle:  # clé présente : on liste les modèles disponibles pour corriger le nom si besoin
            try:
                req = urllib.request.Request(conf["base_url"].rstrip("/") + "/models",
                                             headers={"Authorization": f"Bearer {a.cle}", "User-Agent": "denicheur/1.0 (python)"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    ids = [m.get("id", "") for m in json.loads(r.read()).get("data", [])]
                mot = conf["modele"].split("/")[-1].split("-")[0]
                proches = [i for i in ids if mot.lower() in i.lower()][:25]
                dire(f"   modèles disponibles proches : {proches or ids[:25]}")
            except Exception as e:
                dire(f"   liste des modèles impossible : {type(e).__name__}: {str(e)[:150]}")
    try:
        tok = ebay.jeton()
        prix, ex = ebay.chercher(tok, "ryzen 7 7700", neuf=True, limite=10)
        dire(f"✅ eBay (EBAY_CLIENT_ID / EBAY_CLIENT_SECRET) : fonctionne — {len(prix)} annonces trouvées pour « ryzen 7 7700 »")
    except Exception as e:
        detail = e.read()[:200].decode(errors="replace") if hasattr(e, "read") else str(e)[:200]
        dire(f"❌ eBay : {type(e).__name__} {detail}")
    heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M")
    ecrire("data/verification.json", {"date": heure, "resultats": lignes})


def tester_sources():
    """Teste chaque source candidate (gratuit) et écrit data/test_sources.json."""
    cands = charger("config/sources_candidates.json")["candidates"]
    res = []
    for s_ in cands:
        items, err = collecte.lire_flux(s_)
        avec_prix = sum(1 for a in items if a.get("prix"))
        res.append({**s_, "ok": err is None and len(items) > 0, "nb": len(items), "avec_prix": avec_prix,
                    "erreur": err, "exemple": items[0]["titre"][:90] if items else None})
        print(("✅" if items else "❌"), s_["id"], len(items), "annonces,", avec_prix, "avec prix", err or "")
    ecrire("data/test_sources.json", res)


def tester_rapports():
    """Teste les rapports Demande/Concurrence sur 2 produits connus + l'accès à idealo."""
    import urllib.request
    from . import rapports
    res = {"produits": []}
    tok = ebay.jeton()
    for q, prix in (("Garmin Forerunner 165", 88.66), ("Nike Air Max Dn", 50.0)):
        res["produits"].append({"produit": q, "concurrence": rapports.concurrence(tok, q, prix),
                                "demande": rapports.demande(q)})
    try:
        req = urllib.request.Request("https://www.idealo.fr/prix/207673478/apple-iphone-17-256-go-blanc.html",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            res["idealo"] = {"code": r.status, "taille": len(r.read())}
    except Exception as e:
        res["idealo"] = {"erreur": f"{type(e).__name__}: {str(e)[:150]}"}
    ecrire("data/test_rapports.json", res)
    print(json.dumps(res, ensure_ascii=False)[:3000])


def tester_comparateurs():
    """Teste quels comparateurs un programme peut lire (statut HTTP, taille, prix trouvés)."""
    import re as _re
    import urllib.request
    urls = {
        "idealo": "https://www.idealo.fr/prechcat.html?q=0195951030784",
        "ledenicheur": "https://ledenicheur.fr/search?search=0195951030784",
        "ledenicheur_produit": "https://ledenicheur.fr/product.php?p=16169305",
        "123comparer": "https://www.123comparer.fr/smartphones/gyau1pj3gwauyc3oghhde.html",
        "123comparer_recherche": "https://www.123comparer.fr/recherche/?q=0195951030784",
        "achatmoinscher": "https://www.achatmoinscher.com/recherche.php?q=0195951030784",
        "achatmoinscher_nom": "https://www.achatmoinscher.com/recherche.php?q=apple%20iphone%2017e%20256%20go%20blanc&etat=2",
        "amc_promos_smartphone": "https://www.achatmoinscher.com/comparateur-de-prix-Smartphone/?tri=5&etat=2",
        "amc_deals": "https://www.achatmoinscher.com/deals.php",
        "google_shopping": "https://www.google.com/search?tbm=shop&q=0195951030784",
        "leboncoin": "https://www.leboncoin.fr/recherche?text=iphone%2017e%20256",
        "vinted": "https://www.vinted.fr/catalog?search_text=iphone%2017e",
    }
    from . import comparateurs
    res = {"prix_plancher": {n: comparateurs.prix_plancher(n) for n in (
        "Apple iPhone 17e 256 Go Blanc", "Apple iPhone 17 256 Go Blanc", "Garmin Forerunner 165", "AMD Ryzen 7 9800X3D")}}
    print(json.dumps(res, ensure_ascii=False)[:2500])
    for nom, u in urls.items():
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                                                     "Accept-Language": "fr-FR,fr;q=0.9", "Accept": "text/html,application/xhtml+xml"})
            with urllib.request.urlopen(req, timeout=25) as r:
                h = r.read().decode("utf-8", errors="replace")
            prix = _re.findall(r"(\d{2,4}[,.]\d{2})\s?(?:€|&euro;|&nbsp;€)", h)[:8]
            res[nom] = {"ok": True, "taille": len(h), "prix_vus": prix, "ean_present": "0195951030784" in h}
            if nom in ("amc_promos_smartphone", "123comparer", "ledenicheur_produit", "achatmoinscher_nom"):
                os.makedirs("data/echantillons", exist_ok=True)
                with open(f"data/echantillons/{nom}.html", "w", encoding="utf-8") as f:
                    f.write(h[:400000])
        except Exception as e:
            res[nom] = {"ok": False, "erreur": f"{type(e).__name__}: {str(e)[:120]}"}
        print(nom, res[nom])
    ecrire("data/test_comparateurs.json", res)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--passage", choices=["asie", "europe", "nuit", "midi", "soir"], default="nuit")
    p.add_argument("--test", action="store_true")
    p.add_argument("--verifier", action="store_true", help="tester les 5 clés")
    p.add_argument("--sources", action="store_true", help="tester les sources candidates")
    p.add_argument("--rapports", action="store_true", help="tester les rapports demande/concurrence")
    p.add_argument("--comparateurs", action="store_true", help="tester l'accès aux comparateurs")
    a = p.parse_args()
    if a.comparateurs:
        tester_comparateurs()
    elif a.rapports:
        tester_rapports()
    elif a.sources:
        tester_sources()
    elif a.verifier:
        verifier()
    else:
        passage(a.passage, a.test)


if __name__ == "__main__":
    main()
