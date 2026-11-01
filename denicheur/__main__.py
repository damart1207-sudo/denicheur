"""Lancement : python -m denicheur --passage asie|europe [--test]

--test : aucune connexion, aucune IA appelée (données d'exemple) -> gratuit, pour vérifier le code.
"""
import argparse
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
def passage(nom, test=False):
    maintenant = datetime.now(timezone.utc)
    paris = maintenant.astimezone(ZoneInfo("Europe/Paris"))
    horodatage = paris.strftime("%Y-%m-%d_%H%M")
    regles, conf_eq = charger("config/regles.json"), charger("config/equipe.json")
    with open(os.path.join(RACINE, "skills/methode.md"), encoding="utf-8") as f:
        methode = f.read()
    sources = charger("config/sources.json")["sources"]

    annonces, etat_sources = collecte.collecter(sources, lecteur_test if test else collecte.lire_flux)

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

    # vérification des prix sur Google (Gemini + recherche), puis marge recalculée au prix prudent
    if test:
        bilan_verif = {"faits": 0, "erreurs": ["mode test"]}
    elif nom != "europe":
        bilan_verif = {"faits": 0, "erreurs": ["vérification réservée au passage europe (quota gratuit)"]}
    else:
        conf_v = conf_eq["agents"][conf_eq.get("verificateur", "gemini")]
        modeles_v = [conf_v["modele"]] + list(conf_v.get("modeles_secours", []))[:2]
        bilan_verif = verif.verifier_prix(retenus, cle=os.environ.get(conf_v["cle_env"], "").strip(), modeles=modeles_v, maxi=12)
    # prix réels des annonces eBay (API officielle, gratuite) : tous les passages
    bilan_ebay = {"faits": 0, "erreurs": ["mode test"]} if test else ebay.controler(retenus)
    s_ = regles["seuils"]
    for c in retenus:
        v, plaf_ebay = c.get("verification"), ebay.plafond(c)
        if not v and plaf_ebay is None:
            continue
        plafonds = [c["prix_revente_estime"]]
        if v:
            plafonds.append(v["prix_revente_prudent"])
        if plaf_ebay is not None:
            plafonds.append(plaf_ebay)
        c["prix_revente_prudent"] = min(plafonds)
        cout = c["cout_achat"]
        c["marge_verifiee"] = equipe.marge_nette(c["prix_revente_prudent"], c["plateforme_revente"], cout, regles)
        c["rentabilite_verifiee"] = round(c["marge_verifiee"] / cout, 3) if cout else 0
        neuf_ebay = ((c.get("ebay") or {}).get("neuf") or {}).get("p25")
        c["passe_verif"] = (c["marge_verifiee"] >= s_["marge_nette_min"] and c["rentabilite_verifiee"] >= s_["rentabilite_min"]
                            and not (v and v["deja_moins_cher_ailleurs"])
                            and not (neuf_ebay and neuf_ebay <= c["prix"]))
    retenus.sort(key=lambda c: (c.get("passe_verif", True), c["score"]), reverse=True)
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
        "google_shopping": "https://www.google.com/search?tbm=shop&q=0195951030784",
        "leboncoin": "https://www.leboncoin.fr/recherche?text=iphone%2017e%20256",
        "vinted": "https://www.vinted.fr/catalog?search_text=iphone%2017e",
    }
    res = {}
    for nom, u in urls.items():
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                                                     "Accept-Language": "fr-FR,fr;q=0.9", "Accept": "text/html,application/xhtml+xml"})
            with urllib.request.urlopen(req, timeout=25) as r:
                h = r.read().decode("utf-8", errors="replace")
            prix = _re.findall(r"(\d{2,4}[,.]\d{2})\s?(?:€|&euro;|&nbsp;€)", h)[:8]
            res[nom] = {"ok": True, "taille": len(h), "prix_vus": prix, "ean_present": "0195951030784" in h}
        except Exception as e:
            res[nom] = {"ok": False, "erreur": f"{type(e).__name__}: {str(e)[:120]}"}
        print(nom, res[nom])
    ecrire("data/test_comparateurs.json", res)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--passage", choices=["asie", "europe"], default="europe")
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
