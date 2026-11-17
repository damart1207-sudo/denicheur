"""Robots Apify (testés le 01/11/2026) : idealo, Leboncoin, Vinted. Budget plafonné.

Garde-fous : plafond par appel (maxTotalChargeUsd), et budget mensuel suivi dans data/etat/apify_budget.json :
au-delà de BUDGET_MOIS_USD (35 $ sur le plan Starter), plus aucun appel jusqu'au mois suivant.
"""
import json
import os
import re
import statistics
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import comparateurs, journal, budget

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUDGET_MOIS_USD = 35.0  # plan Starter (19 $ inclus) pris le 03/11/2026 ; plafond Apify côté compte : 40 $/mois
# plafonds par jour (estimés d'après les tarifs) pour que le crédit gratuit tienne tout le mois :
# A (vérifications idealo/Leboncoin/Vinted des alertes) 0,55 $ ; P (idealo des trois passages, à part : le 05/11 la veille avait vidé A avant midi) 0,15 $ ;
# B (tendances) 0,15 $ ; C (chasse ciblée) 0,15 $ ; D (Vinted inter-pays) 0,10 $
# T (affiliation TikTok Shop, outils/affiliation_tiktok.py, 2 relevés par semaine) : 1 $ les jours de relevé.
# Un relevé = 2 classements de 100 produits (0,295 $ chacun, mesuré le 15/11) + recoupements des finalistes (≈ 0,03 $ par marque).
# E (marché des écarts vendeurs, denicheur/marche.py, 17/11/2026) : Vinted + Leboncoin + idealo pour chaque affaire alertée,
# 0,05 $ réservés par affaire (≈ 0,03 $ au réel), soit 8 affaires par jour ; à part pour ne pas prendre sur les vérifications de la veille (A).
PLAFOND_JOUR_USD = {"A": 0.55, "P": 0.30, "B": 0.15, "C": 0.15, "D": 0.10, "E": 0.40, "T": 1.00}  # 1,65 $/jour hors T ; le plafond mensuel prime
# Soirée de mise au point du 15/11/2026 uniquement (plusieurs relevés d'essai, débités au plafond avant le débit réel) :
if datetime.now(timezone.utc).strftime("%Y-%m-%d") == "2026-11-15":
    PLAFOND_JOUR_USD["T"] = 2.00
F_BUDGET = os.path.join(RACINE, "data/etat/apify_budget.json")
# coût réel approximatif : (démarrage, par résultat) en $ — d'après les tarifs Apify relevés le 01/11/2026
TARIFS = {"idealo": (0.0005, 0.003), "leboncoin": (0.005, 0.0008), "vinted": (0.0, 0.001), "idealo_tendances": (0.0001, 0.0005),
          # relevés réels du 15/11/2026 (console Apify de David) : TikTok 0,073 $ pour 25 produits ; eBay 0,018 $ pour 5 ventes ;
          # pubs 0,086 $ pour 42 pubs. TikTok : démarrage 0,025 $ à partir du 23/11/2026 (annoncé par le robot).
          "tiktok_top": (0.025, 0.0027), "ebay_vendus": (0.0, 0.0035), "pubs": (0.0, 0.0021)}
COUT_AU_RESULTAT = {"tiktok_top", "ebay_vendus", "pubs"}
CONTEXTE = {"denicheur": "A"}  # qui appelle (A, B ou C), pour le journal
ROBOTS = {
    "idealo": ("memo23~idealo-scraper", 0.015),  # 08/11 : coût réel ~0,01 $ (3 résultats) ; 0,03 bloquait les passages après 5 appels/jour
    # 17/11/2026 : fatihtahta~leboncoin-fr-scraper ne renvoyait plus AUCUNE annonce depuis le 06/11 (« source connection
    # unavailable », diagnostic outils/diag_leboncoin.py). Remplacé par memo23 : 15 annonces justes en 37 s pour ≈ 0,017 $.
    "leboncoin": ("memo23~leboncoin-scraper", 0.02),
    "vinted": ("scrape.badger~vinted-scraper", 0.03),
    # affiliation TikTok Shop (testés le 15/11/2026, voir outils/affiliation_tiktok.py)
    # 4 catégories × 25 produits (25 = minimum accepté par le robot) = 100 lignes × 0,0027 $ + démarrage 0,025 $ = 0,295 $
    "tiktok_top": ("lergassy~tiktok-shop-top-products-scraper", 0.30),   # classement des ventes TikTok Shop France + commission
    "ebay_vendus": ("caffein.dev~ebay-sold-listings", 0.04),            # prix réellement vendus sur ebay.fr
    "pubs": ("apivault_labs~ad-library-scraper-facebook-tiktok-google-ads", 0.04),  # pubs Facebook / Instagram / Google
}


def _budget():
    mois = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        with open(F_BUDGET) as source:
            b = json.load(source)
    except (OSError, json.JSONDecodeError):
        b = {}
    if b.get("mois") != mois:
        b = {"mois": mois, "depense_estimee_usd": 0.0, "appels": 0}
    return b


def _noter(b, cout):
    b["depense_estimee_usd"] = round(b["depense_estimee_usd"] + cout, 4)
    b.pop("depense_ce_tour", None)  # ancien cumul persistant, pas un compteur de tour
    _reel["reserves_processus"] = round(_reel.get("reserves_processus", 0) + cout, 4)
    b["depense_reelle_usd"] = _reel.get("usd")
    b["appels"] += 1
    os.makedirs(os.path.dirname(F_BUDGET), exist_ok=True)
    with open(F_BUDGET, "w") as sortie:
        json.dump(b, sortie, indent=1)


_reel = {}


def depense_reelle():
    """Dépense réelle du mois lue chez Apify (appel gratuit), une fois par lancement."""
    if "usd" not in _reel:
        try:
            req = urllib.request.Request("https://api.apify.com/v2/users/me/limits",
                                         headers={"Authorization": f"Bearer {os.environ['APIFY_TOKEN'].strip()}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                _reel["usd"] = float(json.loads(r.read())["data"]["current"]["monthlyUsageUsd"])
        except Exception:
            _reel["usd"] = None
    return _reel["usd"]


def depense_du_jour(denicheur):
    return sum(l.get("cout_usd", 0) for l in journal.lire(1)
               if l.get("jour") == datetime.now(timezone.utc).strftime("%Y-%m-%d")
               and l["denicheur"] == denicheur and l["source"].startswith("apify:"))


def disponible():
    if not os.environ.get("APIFY_TOKEN", "").strip():
        return False
    den = CONTEXTE["denicheur"]
    if depense_du_jour(den) >= PLAFOND_JOUR_USD.get(den, 0.03):
        return False
    reel = depense_reelle()
    if reel is None:  # impossible de lire la dépense : prudence, on s'arrête
        return False
    # Le registre partagé reste l'autorité. Ne pas réadditionner les anciens
    # appels déjà présents dans la mesure fournisseur à chaque redémarrage.
    return max(reel + _reel.get("reserves_processus", 0),
               _budget().get("depense_estimee_usd", 0)) < BUDGET_MOIS_USD


def lancer(robot, entree, maxi=10):
    """Lance un robot (synchrone). Renvoie la liste des résultats, ou None si budget/jeton absent ou erreur."""
    acteur, plafond = ROBOTS[robot]
    return _lancer(robot, acteur, plafond, entree, maxi)


def lancer_test(nom, acteur, entree, maxi=10):
    """Sonde réelle : même registre et catégorie A, plafond fixe de 0,05 $.

    Cette fonction n'est pas un mode gratuit. Les tests hors réseau la simulent.
    """
    return _lancer("test:" + nom, acteur, 0.05, entree, maxi)


_VERROU = threading.RLock()  # les recherches du marché partent en parallèle : budget et journal un seul à la fois


def _lancer(robot, acteur, plafond, entree, maxi):
    with _VERROU:
        if not disponible():
            return None
        b = _budget()
        categorie = CONTEXTE['denicheur']
        try:
            reservation = budget.reserver('apify', plafond, sum(PLAFOND_JOUR_USD.values()), BUDGET_MOIS_USD,
                categorie=categorie, plafond_categorie=PLAFOND_JOUR_USD.get(categorie, 0.03),
                deja_jour=sum(depense_du_jour(c) for c in PLAFOND_JOUR_USD),
                deja_mois=max(depense_reelle() or 0, b.get('depense_estimee_usd', 0)),
                deja_categorie=depense_du_jour(categorie))
        except budget.Indisponible:
            return None
        if reservation is None:
            return None
    url = (f"https://api.apify.com/v2/acts/{acteur}/run-sync-get-dataset-items?"
           + urllib.parse.urlencode({"timeout": 150, "maxItems": maxi, "maxTotalChargeUsd": plafond}))
    req = urllib.request.Request(url, data=json.dumps(entree).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ['APIFY_TOKEN'].strip()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=200) as r:
            items = json.loads(r.read() or b"[]")
    except Exception:
        items = None
    n = len(items) if isinstance(items, list) else 0
    dep, unit = TARIFS.get(robot, (0.0, plafond / max(maxi, 1)))
    # Le nombre de résultats n'est pas une facture. Aucun remboursement de
    # réservation à partir d'un tarif estimé ; conserver le plafond engagé.
    debit = plafond
    with _VERROU:
        if isinstance(items, list):
            budget.rapprocher('apify', reservation, debit)
        # Un timeout ne signifie pas que l'acteur s'est arrêté ; aucune relance automatique (le plafond reste débité).
        _noter(_budget(), debit)   # relu : un autre appel a pu écrire pendant celui-ci
        journal.noter(categorie, "apify:" + robot, _cible(entree), cout_usd=dep + unit * n, resultats=n)
    return items if isinstance(items, list) else None


def _cible(entree):
    """Ce qui a été cherché, en texte court pour le journal (les robots attendent tantôt un texte, tantôt une liste)."""
    for cle in ("searchQuery", "query", "keywords", "categories", "domains", "startUrls"):
        v = entree.get(cle)
        if v:
            if isinstance(v, (list, tuple)):
                v = ",".join(x.get("url", "") if isinstance(x, dict) else str(x) for x in v)
            return str(v)[:80]
    return ""


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d[\d\s.,]*", str(v or ""))
    return comparateurs._prix(m.group(0)) if m else None


def prix_idealo(nom, ean=None):
    """Prix neuf le plus bas en France sur idealo pour CE produit exact.
    11/11 : avec un code EAN, la recherche se fait par EAN (les longs titres Amazon ne trouvaient rien sur idealo)."""
    ean = str(ean).strip() if ean else ""
    items = lancer("idealo", {"searchQuery": ean or nom, "country": "FR", "maxItems": 3, "fetchOffers": False}, maxi=3)
    if not items:
        return None
    def _ok(i):
        if ean and str(i.get("gtin") or "").lstrip("0") == ean.lstrip("0"):
            return True
        if ean and len(items) == 1:
            return True  # idealo renvoie la fiche exacte pour un EAN
        return comparateurs.correspond(i.get("title", ""), nom)
    bons = [i for i in items if isinstance(i, dict) and i.get("price") and _ok(i)]
    if not bons:
        return None
    b = min(bons, key=lambda i: i["price"])
    return {"prix_min": float(b["price"]), "nb_offres": b.get("offerCount"), "lien": b.get("url"), "titre": b.get("title"),
            "gtin": b.get("gtin")}


def annonces_leboncoin(nom, maxi=15, plafond=None):
    """Annonces Leboncoin en cours pour une recherche : [(titre, prix, lien, date de 1re publication)].
    None si le robot n'a pas pu être lancé."""
    acteur, defaut = ROBOTS["leboncoin"]
    items = _lancer("leboncoin", acteur, plafond or defaut,
                    {"startUrls": [{"url": "https://www.leboncoin.fr/recherche?text=" + urllib.parse.quote(nom)}], "maxItems": maxi}, maxi)
    if items is None:
        return None
    out = []
    for i in items:
        p = _num(i.get("price")) if isinstance(i, dict) else None
        if p and i.get("title"):
            out.append((i["title"], p, i.get("url"), i.get("firstPublishedAt") or i.get("indexedAt")))
    return out


def revente_reelle(nom, prix_achat, avec_liens=False):
    """Prix des annonces réelles en cours (neuf ou comme neuf) sur Vinted et Leboncoin."""
    res = {}
    v = lancer("vinted", {"mode": "Search Items", "query": nom, "market": "fr", "max_results": 15}, maxi=15) or []
    pv = [float(i["price_amount"]) for i in v if isinstance(i, dict) and i.get("price_amount")
          and comparateurs.correspond(i.get("title", ""), nom) and "neuf" in (i.get("status") or "").lower()]
    pv = [p for p in pv if p >= prix_achat * 0.5]
    if pv:
        res["vinted"] = {"nb": len(pv), "min": min(pv), "mediane": statistics.median(pv),
                         "lien_min": next((i.get("url") for i in v if isinstance(i, dict) and i.get("price_amount") and float(i["price_amount"]) == min(pv)), None)}
    pl = [p for t, p, _, _ in annonces_leboncoin(nom) or [] if comparateurs.correspond(t, nom) and p >= prix_achat * 0.5]
    if pl:
        res["leboncoin"] = {"nb": len(pl), "min": min(pl), "mediane": statistics.median(pl)}
    return res
