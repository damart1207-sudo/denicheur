"""AFFILIATION TIKTOK SHOP : quels produits promouvoir en vidéo ? (demande de David, 15/11/2026)

Chaîne (4 sources prouvées le 15/11/2026 par de vrais relevés) :
 1. DEUX classements TikTok Shop France sur 7 jours, avec la commission d'affiliation (robot Apify « tiktok_top ») :
    les plus vendus (valeurs sûres, déjà très promues) et les plus fortes hausses parmi les produits qui font déjà un vrai
    chiffre (plancher « revenu_min_usd » : sans lui, la liste du 15/11 était faite de produits à 11 ventes sans commission).
    Un produit présent dans les deux listes est un BINGO : il se vend déjà et il accélère encore ;
 2. tri : gain par vente (prix moyen × commission), volume, évolution -> quelques finalistes, en variant marques et catégories ;
 3. pour chaque finaliste : prix chez les marchands français (Google Shopping par DataForSEO, 0,002 $ la recherche) :
    « même produit » si la marque et le type correspondent, « produits équivalents » (fourchette) pour un sans-marque au
    titre précis, rien si le titre est trop vague ; puis prix réellement vendus sur ebay.fr (robot « ebay_vendus »), pubs Facebook / Instagram / Google
    en cours (robot « pubs » : une pub payée depuis des semaines = un produit qui se vend), prix Amazon.fr (Keepa) ;
 4. pour décider entre l'affiliation et la vente ailleurs (demande de David, 19/11/2026) : le meilleur prix neuf du même
    produit ailleurs (le plus bas entre Google Shopping et Amazon.fr) et le volume de recherche mensuel Google France
    (DataForSEO Labs, un appel groupé ≈ 0,02 $ par relevé).
Aucun chiffre inventé : une donnée absente est écrite « non trouvé ». Les montants TikTok sont des ESTIMATIONS du
fournisseur de données, en dollars (à utiliser pour comparer les produits entre eux).

Coût : ≈ 0,70 $ par relevé (2 classements de 100 produits ≈ 0,59 $ + recoupements ≈ 0,10 $) (plafond du jour « T » dans denicheur/apify.py), Keepa ≈ 10 jetons par finaliste.
Un classement n'est payé qu'une fois par jour, et un relevé complet n'est pas refait le même jour (sauf AFFIL_FORCER=1).
Lancement : outil = affiliation_tiktok  ->  data/affiliation_tiktok.html + data/affiliation_tiktok.json + Telegram
Réglages : config/affiliation_tiktok.json"""
import html as H
import json
import os
import re
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from denicheur import apify, dataforseo, keepa, sante, shopping, telegram  # noqa: E402

F_CONFIG = os.path.join(RACINE, "config/affiliation_tiktok.json")
F_JSON = os.path.join(RACINE, "data/affiliation_tiktok.json")
F_HTML = os.path.join(RACINE, "data/affiliation_tiktok.html")
F_RESERVE = os.path.join(RACINE, "data/etat/affiliation_comparaison.json")
MOTS_MARQUE_INUTILES = re.compile(r"\b(officiel(le)?|official|pm|store|shop|france|fr)\b", re.I)


# ---------- calculs purs (testés hors réseau : tests/test_affiliation_tiktok.py) ----------

def nombre(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


ETIQUETTE_PROMO = re.compile(r"exclusivit|live|black\s*friday|promo|offre|nouveau|new|soldes|no[ëe]l|cadeau|pack|lot\b", re.I)


def sans_etiquettes(titre):
    """Retire les étiquettes promotionnelles en tête : « [EXCLUSIVITÉ LIVE] medicube … », « 【Black Friday】GaaliShop … »."""
    titre = (titre or "").strip()
    while True:
        m = re.match(r"\s*[\[【]([^\]】]+)[\]】]\s*", titre)
        if not m or not ETIQUETTE_PROMO.search(m.group(1)):
            return titre
        titre = titre[m.end():]


def marque(titre):
    """Marque probable : le texte entre crochets en tête (« [medicube Officiel] »), sinon le premier mot."""
    titre = sans_etiquettes(titre)
    m = re.match(r"\s*\[([^\]]+)\]", titre)
    if m:
        return re.sub(r"\s+", " ", MOTS_MARQUE_INUTILES.sub(" ", m.group(1))).strip()
    mots = titre.split()
    return mots[0].strip(",;:") if mots else ""


def mot_cle(titre, mots=4):
    """Titre TikTok (très long) -> recherche courte : marque + premiers mots avant le premier séparateur."""
    titre = (titre or "").strip()
    m = marque(titre) if titre.startswith("[") else ""
    corps = re.sub(r"\[[^\]]*\]", " ", titre)
    corps = re.split(r"\s[|–—-]\s|[,(]", corps)[0]
    return " ".join(([m] if m else []) + corps.split()[:mots]).strip()


PAS_UNE_MARQUE = {"LOT", "PACK", "NEW", "PROMO", "KIT", "SET", "XXL", "LED", "USB", "STEM", "PVC", "BLACK", "FRIDAY", "NOEL", "NOËL",
                  "CADEAU", "COFFRET", "OFFRE", "SOLDES", "VARIANTES", "FRANCE", "BIO", "PRO", "MAX", "MINI", "PLUS"}


def marque_fiable(titre):
    """Marque dont on est sûr, sinon "" (relevé du 15/11/2026 : sans marque, eBay, Amazon et les pubs renvoyaient
    d'AUTRES produits — « Coffret de Noël » ramenait un coffret de thés, « Manteau » des annonceurs nommés Manteau).
    Trois cas acceptés : marque entre crochets en tête ; premiers mots tout en majuscules (« LANDOT », « CP PAPILLON ») ;
    un seul mot à majuscule après le dernier « - » (« … - Garnier »)."""
    titre = sans_etiquettes(titre)
    if titre.startswith("["):
        return marque(titre)
    debut = []
    for mot in titre.split():
        m = mot.strip(",;:|")
        if len(m) >= 2 and m.isalpha() and m.isupper() and m not in PAS_UNE_MARQUE:
            debut.append(m)
        else:
            break
    if debut and max(len(m) for m in debut) >= 3:
        return " ".join(debut)
    fin = re.split(r"\s[–—-]\s", titre)
    if len(fin) > 1:
        dernier = fin[-1].strip()
        if re.fullmatch(r"[A-ZÀ-Ý][a-zà-ÿ]{2,}", dernier):
            return dernier
    return ""


def recherche(titre, marque_sure, mots=3):
    """Recherche courte et précise : la marque sûre + les premiers mots du produit."""
    corps = re.sub(r"\[[^\]]*\]", " ", titre or "")
    corps = re.split(r"\s[|–—-]\s|[,(]", corps)[0]
    reste = [m for m in corps.split() if m.strip(",;:").lower() not in {x.lower() for x in marque_sure.split()}]
    return " ".join([marque_sure] + reste[:mots]).strip()


def _sans_accent(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


UNITES = {"ml", "cl", "kg", "mg", "cm", "mm", "spf", "pcs", "edp", "edt"}
MOTS_VIDES = {"les", "des", "pour", "avec", "sans", "une", "aux", "the", "and", "for", "with", "sur", "par", "est", "son", "ses",
              "peau", "soin", "soins", "visage", "officiel", "official", "beauty"}


def mots(texte):
    return [m for m in re.findall(r"[a-z0-9]+", _sans_accent(texte)) if len(m) >= 3 and m not in MOTS_VIDES and m not in UNITES]


def mots_distinctifs(titre, marque_sure):
    """Les mots qui identifient le modèle : sigles et références (« NAD+ », « EGF », « PDRN », « HS08 »), dans l'ordre du titre."""
    m = set(mots(marque_sure))
    vus, out = set(), []
    for brut in re.findall(r"[A-Za-zÀ-ÿ0-9+]+", re.sub(r"\[[^\]]*\]", " ", titre or "")):
        coeur = brut.strip("+")
        sigle = len(coeur) >= 3 and coeur.isalpha() and coeur.isupper() and coeur not in PAS_UNE_MARQUE
        reference = len(coeur) >= 3 and any(c.isdigit() for c in coeur) and any(c.isalpha() for c in coeur)
        n = _sans_accent(coeur)
        if (sigle or reference) and n not in m and n not in UNITES and not re.fullmatch(r"\d+(ml|g|kg|cm|mm|h|pcs)", n) and n not in vus:
            vus.add(n)
            out.append(coeur)
    return out


def recherche_precise(titre, marque_sure):
    """Pour eBay et Amazon, où les titres changent de langue : la marque + 2 sigles/références du modèle, sinon 2 mots."""
    d = mots_distinctifs(titre, marque_sure)[:2]
    return " ".join([marque_sure] + d) if d else recherche(titre, marque_sure, mots=2)


def asins_des_pubs(pubs):
    """Les fiches amazon.fr vers lesquelles la marque envoie elle-même ses pubs : c'est le lien le plus sûr vers le bon produit."""
    out = []
    for l in pubs or []:
        m = re.search(r"amazon\.fr/(?:[^/?#]+/)?(?:dp|gp/product)/([A-Z0-9]{10})", str(l.get("landingUrl") or ""))
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def ressemblance(titre_tiktok, titre_amazon, marque_sure):
    """Nombre de mots du modèle partagés (un sigle ou une référence compte double). 0 si la marque manque."""
    if not marque_sure or _sans_accent(marque_sure).replace(" ", "") not in _sans_accent(titre_amazon).replace(" ", ""):
        return 0
    a = set(mots(titre_amazon))
    m = set(mots(marque_sure))
    d = {_sans_accent(x) for x in mots_distinctifs(titre_tiktok, marque_sure)}
    communs = (set(mots(re.sub(r"\[[^\]]*\]", " ", titre_tiktok))) - m) & a
    return len(communs) + len(communs & d)


def choisir_amazon(titre_tiktok, fiches, marque_sure, seuil=3):
    """La fiche Amazon qui ressemble le plus au produit TikTok, si elle partage assez de mots du modèle ; sinon None."""
    notes = [(ressemblance(titre_tiktok, f.get("titre"), marque_sure), f) for f in fiches
             if isinstance(f, dict) and not f.get("erreur") and f.get("prix_neuf")]
    notes.sort(key=lambda x: -x[0])
    if not notes or notes[0][0] < seuil or (len(notes) > 1 and notes[1][0] == notes[0][0]):
        return None  # pas assez ressemblant, ou deux fiches à égalité : on ne tranche pas au hasard
    return notes[0][1]


def garder_ventes(lignes, marque_sure):
    """Ne garde que les ventes eBay dont le titre contient la marque (sinon ce n'est pas le même produit)."""
    m = _sans_accent(marque_sure)
    return [l for l in lignes or [] if isinstance(l, dict) and m and m in _sans_accent(l.get("title"))]


def garder_pubs(lignes, marque_sure):
    """Ne garde que les pubs de la marque : annonceur dont le nom COMMENCE par la marque, ou lien qui la contient
    (« Sébastien Roland Jean LANDOT » est une personne, pas la marque LANDOT)."""
    m = _sans_accent(marque_sure).replace(" ", "")
    bons = []
    for l in lignes or []:
        if not isinstance(l, dict) or not m:
            continue
        nom = _sans_accent(l.get("advertiserName") or l.get("resolvedBrand")).replace(" ", "")
        lien = _sans_accent(str(l.get("landingUrl") or "") + " " + str(l.get("destinationDomain") or "")).replace("-", "")
        if nom.startswith(m) or m in lien:
            bons.append(l)
    return bons


def lien_appli(url):
    """Lien qui ouvre la fiche dans l'appli TikTok. Les liens du robot (shop.tiktok.com/fr/pdp/…) renvoient à l'accueil avec
    « région non prise en charge » : les fiches françaises ne s'affichent pas dans un navigateur (constaté le 15/11/2026).
    Le format /view/product/ a été vérifié par David sur son téléphone le 15/11/2026."""
    m = re.search(r"(?:/pdp/(?:[^/?#]*/)?|/view/product/|/product/)(\d{10,})", str(url or ""))
    return f"https://www.tiktok.com/view/product/{m.group(1)}" if m else str(url or "")


def categorie_principale(texte):
    """Le robot renvoie toute la liste des sous-catégories (« Home Supplies | Home Supplies-Home Decor | … ») : on garde la première."""
    return str(texte or "").split(" | ")[0].strip()


def lire_produit(ligne):
    """Une ligne du robot TikTok -> produit normalisé, ou None si ce n'est pas une ligne produit (notice, erreur)."""
    if not isinstance(ligne, dict) or not ligne.get("title"):
        return None
    ventes, prix, com = nombre(ligne.get("unitsSold")), nombre(ligne.get("avgSellingPrice")), nombre(ligne.get("commissionRatePercent"))
    if ventes is None or prix is None or com is None:
        return None
    revenu = nombre(ligne.get("revenue")) or 0.0
    video = nombre(ligne.get("videoRevenue"))
    return {
        "titre": str(ligne["title"]).strip(),
        "marque": marque(ligne["title"]),
        "categorie": categorie_principale(ligne.get("category") or ligne.get("sourceInput")),
        "rang": ligne.get("rank"),
        "ventes_7j": int(ventes),
        "prix_moyen_usd": round(prix, 2),
        "commission_pct": com,
        "gain_par_vente_usd": round(prix * com / 100, 2),
        "revenu_usd": round(revenu),
        "commissions_totales_usd": round(revenu * com / 100),
        "part_video_pct": round(100 * video / revenu) if video is not None and revenu > 0 else None,
        "evolution_pct": nombre(ligne.get("revenueGrowthPercent")),
        "lien": lien_appli(ligne.get("url")),
    }


def retenu(p, filtres):
    """Renvoie (True, "") ou (False, raison écrite pour David)."""
    if re.search(r"exclusivit[ée]s?\s+live", p["titre"], re.I):
        return False, "réservé aux lives"
    if p["prix_moyen_usd"] < filtres["prix_moyen_min_usd"]:
        return False, "prix moyen trop bas (donnée douteuse ou gain infime)"
    hausse = "hausses" in (p.get("listes") or [])  # liste déjà filtrée sur le chiffre d'affaires : moins de ventes exigées
    if p["ventes_7j"] < (filtres.get("ventes_min_hausses", filtres["ventes_min"]) if hausse else filtres["ventes_min"]):
        return False, "trop peu de ventes"
    if p["evolution_pct"] is not None and p["evolution_pct"] < filtres["evolution_min_pct"]:
        return False, "ventes en recul"
    if p["gain_par_vente_usd"] < filtres["gain_par_vente_min_usd"]:
        return False, "gain par vente trop faible"
    return True, ""


LIBELLES = {"plus_vendus": "classement des plus vendus", "hausses": "classement des plus fortes hausses"}


def fusionner(classements):
    """{nom de liste: [produits]} -> produits uniques (par lien), chacun avec ses listes ; bingo = présent dans les deux."""
    par_lien = {}
    for nom, produits in classements.items():
        for p in produits or []:
            x = par_lien.setdefault(p["lien"], dict(p, listes=[]))
            if nom not in x["listes"]:
                x["listes"].append(nom)
    for x in par_lien.values():
        x["bingo"] = len(x["listes"]) >= 2
    return list(par_lien.values())


def trouve_par(p):
    listes = p.get("listes") or ["plus_vendus"]
    if p.get("bingo"):
        return "BINGO : présent dans les deux classements (plus vendus et plus fortes hausses)"
    return LIBELLES.get(listes[0], listes[0])


def choisir_finalistes(produits, filtres, n=3):
    """Tourniquet entre trois familles pour ne fermer aucune piste : un bingo, un produit en hausse, un produit très vendu,
    et on recommence. Dans chaque famille, le plus gros total de commissions d'abord. Jamais deux fois la même marque ;
    les catégories sont réparties (puis complétées s'il reste de la place)."""
    bons = [p for p in produits if retenu(p, filtres)[0]]
    total = lambda p: -p["commissions_totales_usd"]  # noqa: E731
    bingos = sorted((p for p in bons if p.get("bingo")), key=total)
    hausses = sorted((p for p in bons if not p.get("bingo") and "hausses" in (p.get("listes") or [])), key=total)
    vendus = sorted((p for p in bons if not p.get("bingo") and "hausses" not in (p.get("listes") or [])), key=total)
    nb_cat = len({p["categorie"] for p in bons}) or 1
    par_categorie_max = max(1, -(-n // nb_cat))
    choisis, marques, compte = [], set(), {}

    def prendre(famille, limite_categorie):
        for p in famille:
            m = p["marque"].lower()
            if p in choisis or m in marques or (limite_categorie and compte.get(p["categorie"], 0) >= par_categorie_max):
                continue
            choisis.append(p)
            marques.add(m)
            compte[p["categorie"]] = compte.get(p["categorie"], 0) + 1
            return True
        return False

    for limite in (True, False):  # passe 1 : catégories réparties ; passe 2 : on complète sans cette limite
        avance = True
        while avance and len(choisis) < n:
            avance = False
            for famille in (bingos, hausses, vendus):
                if len(choisis) < n and prendre(famille, limite):
                    avance = True
    return choisis


def resume_ebay(lignes):
    prix = [x for x in (nombre(l.get("soldPrice")) for l in lignes or [] if isinstance(l, dict)) if x]
    if not prix:
        return None
    return {"nb": len(prix), "min": min(prix), "mediane": round(statistics.median(prix), 2), "max": max(prix),
            "devise": next((l.get("soldCurrency") for l in lignes if isinstance(l, dict) and l.get("soldCurrency")), "EUR")}


def resume_pubs(lignes):
    pubs = [l for l in lignes or [] if isinstance(l, dict) and l.get("platform")]
    if not pubs:
        return None
    jours = [int(j) for j in (nombre(l.get("daysRunning")) for l in pubs) if j is not None]
    annonceurs = {}
    for l in pubs:
        a = str(l.get("advertiserName") or l.get("resolvedBrand") or "").strip()
        if a:
            annonceurs[a] = annonceurs.get(a, 0) + 1
    vers_amazon = sum(1 for l in pubs if "amazon." in str(l.get("landingUrl") or l.get("destinationDomain") or ""))
    return {"nb": len(pubs), "plus_longue_jours": max(jours) if jours else None,
            "depuis_30j_ou_plus": sum(1 for j in jours if j >= 30),
            "annonceurs": sorted(annonceurs, key=lambda a: -annonceurs[a])[:3], "vers_amazon": vers_amazon}


# ---------- comparaison avec les marchands français (calculs purs) ----------

VERSION_COMPARAISON = 2  # à augmenter quand le tri des offres change : recalcul gratuit à partir des offres enregistrées
OCCASION = re.compile(r"leboncoin|ebay|vinted|back ?market|rakuten|rebuy|occasion|reconditionn", re.I)


def _racine(m):
    return m[:-1] if len(m) > 3 and m[-1] in "sx" else m


def noyau(titre, marque_sure="", n=4):
    """Les premiers mots qui disent ce qu'est le produit (sans la marque), au singulier, sans accent."""
    m = {_racine(x) for x in mots(marque_sure)}
    out = []
    for x in mots(re.sub(r"\[[^\]]*\]", " ", sans_etiquettes(titre))):
        x = _racine(x)
        if x not in m and x not in out:
            out.append(x)
    return out[:n]


def requete_comparaison(titre, marque_sure, mots_min=6):
    """(requête, type) : « meme_produit » avec une marque sûre ; « equivalents » pour un sans-marque au titre précis ;
    (None, "titre_vague") sinon — « Mini box » ou « Manteau bloom » ramèneraient n'importe quoi."""
    if marque_sure:
        return recherche(titre, marque_sure, mots=3), "meme_produit"
    propre = re.sub(r"[–—|,;:()\[\]【】]", " ", sans_etiquettes(titre))
    if len(mots(propre)) < mots_min:
        return None, "titre_vague"
    return " ".join(propre.split()[:7]), "equivalents"


def comparer_offres(offres, titre, marque_sure, genre, prix_tiktok_eur):
    """Offres Google Shopping -> résumé. On ne garde que le neuf en euros qui partage les mots du produit
    (et la marque pour « même produit ») : un boucleur LANDOT n'est pas la brosse LANDOT (test du 15/11/2026)."""
    coeur = noyau(titre, marque_sure, 3 if genre == "meme_produit" else 4)
    besoin = 2 if genre == "meme_produit" else max(2, -(-3 * len(coeur) // 4))
    marque_n = _sans_accent(marque_sure).replace(" ", "")
    nombres = [x for x in coeur if x.isdigit()]  # « 100 blocs » : un jeu de 80 pièces n'est pas un équivalent
    bonnes = []
    for o in offres or []:
        t = o.get("titre") or ""
        if not isinstance(o.get("prix"), (int, float)) or o["prix"] <= 0 or (o.get("devise") not in (None, "", "EUR")):
            continue
        if OCCASION.search(str(o.get("marchand") or "")) or OCCASION.search(t):
            continue
        if marque_n and marque_n not in _sans_accent(t).replace(" ", ""):
            continue
        dans_titre = {_racine(x) for x in mots(t)}
        if len(dans_titre & set(coeur)) < min(besoin, len(coeur)) or any(n not in dans_titre for n in nombres):
            continue
        bonnes.append(o)
    if len(bonnes) >= 3:  # prix aberrants (lot de 50 boîtes à 1 438 €, accessoire à 2 €) : hors de la fourchette médiane ÷ 3 à médiane × 3
        med = statistics.median(o["prix"] for o in bonnes)
        bonnes = [o for o in bonnes if med / 3 <= o["prix"] <= med * 3]
    minimum = 1 if genre == "meme_produit" else 3  # une fourchette d'équivalents demande au moins 3 offres
    if len(bonnes) < minimum:
        return {"type": "aucune", "genre": genre, "nb_lues": len(offres or []), "v": VERSION_COMPARAISON}
    prix = sorted(o["prix"] for o in bonnes)
    bas = min(bonnes, key=lambda o: o["prix"])
    r = {"type": genre, "v": VERSION_COMPARAISON, "nb": len(bonnes), "nb_lues": len(offres or []), "min": prix[0], "max": prix[-1],
         "mediane": round(statistics.median(prix), 2),
         "moins_cher": {"marchand": bas.get("marchand"), "prix": bas["prix"], "titre": (bas.get("titre") or "")[:90], "lien": bas.get("lien")}}
    if prix_tiktok_eur:
        r["prix_tiktok_eur"] = round(prix_tiktok_eur, 2)
        r["ecart_eur"] = round(prix[0] - prix_tiktok_eur, 2)  # positif : TikTok est moins cher que la moins chère des offres
    return r


def texte_comparaison(c):
    """Phrase lisible par David, ou "" s'il n'y a rien à dire."""
    if not isinstance(c, dict):
        return ""
    t = c.get("type")
    if t == "titre_vague":
        return "non comparé : titre trop vague pour chercher ailleurs sans risque de confusion"
    if t == "non_lu":
        return "non lu (budget du jour atteint ou service indisponible)"
    if t == "aucune":
        return f"aucune offre comparable chez les marchands français ({c.get('nb_lues', 0)} offre(s) lue(s), aucune assez proche)"
    if t not in ("meme_produit", "equivalents"):
        return ""
    bas = c["moins_cher"]
    if t == "meme_produit":
        debut = (f"même produit à partir de {_eur(c['min'])} € chez {bas.get('marchand') or 'un marchand'}"
                 + (f" ({c['nb']} offres, jusqu'à {_eur(c['max'])} €)" if c["nb"] > 1 else ""))
    else:
        debut = (f"produits équivalents (pas forcément le même) : de {_eur(c['min'])} à {_eur(c['max'])} €, "
                 f"médiane {_eur(c['mediane'])} € sur {c['nb']} offres")
    e = c.get("ecart_eur")
    if e is None:
        return debut
    tk = f" ; TikTok ≈ {_eur(c['prix_tiktok_eur'])} €, "
    if t == "equivalents":
        # Des équivalents ne sont pas le même produit (tailles, qualités) : on situe TikTok par rapport au prix médian,
        # pas par rapport au moins cher (relevé du 16/11 : « 24 € plus cher » qu'un lot d'assiettes sans rapport).
        m = c["mediane"] - c["prix_tiktok_eur"]
        if abs(m) <= 0.10 * c["mediane"]:
            return debut + tk + "dans les prix du marché"
        return debut + tk + (f"soit {_eur(m)} € de moins que le prix médian" if m > 0 else f"soit {_eur(-m)} € de plus que le prix médian")
    if e > 0.5:
        fin = tk + f"soit {_eur(e)} € de moins"
    elif e < -0.5:
        fin = tk + f"soit {_eur(-e)} € PLUS CHER"
    else:
        fin = tk + "même prix"
    return debut + fin


# ---------- demande sur Google et meilleur prix ailleurs (calculs purs) ----------

PETITS_MOTS = {"de", "du", "des", "le", "la", "les", "un", "une", "et", "a", "à", "au", "aux", "en", "pour", "avec", "sans", "sur",
               "the", "for", "with", "and", "of"}


def mots_google(titre, marque_sure, maxi=6):
    """Mots-clés à mesurer sur Google France : [(mot, genre)]. « marque » = la marque seule puis la marque + le produit
    (demande pour CE produit) ; « produit » = le type de produit sans la marque (demande du marché). Plusieurs longueurs
    sont demandées car un mot-clé tiré d'un titre n'a souvent aucun volume (constat du 04/11) : seuls ceux qui en ont
    un sont affichés, avec le mot exact mesuré."""
    corps = re.sub(r"\[[^\]]*\]", " ", sans_etiquettes(titre))
    corps = re.split(r"\s[|–—-]\s|[,(]", corps)[0]
    de_la_marque = {x.lower() for x in (marque_sure or "").split()}
    reste = [m.strip(",;:+").lower() for m in corps.split()]
    reste = [m for m in reste if m and m not in de_la_marque]
    while reste and reste[0].isdigit():  # « 12 Empty Baskets » : le nombre du lot n'est pas le produit
        reste.pop(0)

    def debut(n):
        x = reste[:n]
        while x and x[-1] in PETITS_MOTS:
            x.pop()
        return " ".join(x)

    out = []

    def ajouter(mot, genre):
        mot = " ".join(mot.split())
        if len(mot) >= 4 and mot not in [o[0] for o in out]:
            out.append((mot, genre))

    if marque_sure:
        m = " ".join(marque_sure.lower().split())
        ajouter(m, "marque")
        sigles = " ".join(mots_distinctifs(titre, marque_sure)[:2]).lower()  # « medicube nad egf » : le nom que les gens tapent
        if sigles:
            ajouter(m + " " + sigles, "marque")
        for n in (2, 3):
            if debut(n):
                ajouter(m + " " + debut(n), "marque")
    for n in ((1, 2, 3) if marque_sure else (1, 2, 3, 4, 5)):
        ajouter(debut(n), "produit")
    return out[:maxi]


def _entier(v):
    return f"{v:,}".replace(",", " ")


def texte_google(g, maxi=4):
    """Phrase lisible par David : les mots-clés mesurés et leur volume mensuel, ou "" si rien n'a été demandé."""
    if not isinstance(g, dict):
        return ""
    if not g.get("lu"):
        return "non lu (budget du jour atteint ou service indisponible)"
    connus = [x for x in g.get("mots") or [] if isinstance(x.get("volume"), int)]
    if not connus:
        essayes = ", ".join(f"« {x['mot']} »" for x in g.get("mots") or [])
        return "aucun volume connu" + (f" pour {essayes}" if essayes else "")
    return " · ".join(f"« {x['mot']} » : {_entier(x['volume'])} par mois" for x in connus[:maxi])


def meilleur_prix(p, taux):
    """Le prix neuf le plus bas trouvé ailleurs pour le MÊME produit (marchands français de Google Shopping et fiche
    Amazon.fr), comparé au prix moyen TikTok. None si le même produit n'a été trouvé nulle part."""
    c, am = p.get("comparaison") or {}, p.get("amazon") or {}
    pistes = []
    if c.get("type") == "meme_produit" and isinstance(c.get("min"), (int, float)):
        bas = c.get("moins_cher") or {}
        pistes.append({"prix": c["min"], "marchand": bas.get("marchand") or "un marchand", "lien": bas.get("lien")})
    if isinstance(am.get("prix_neuf_eur"), (int, float)) and am["prix_neuf_eur"] > 0:
        pistes.append({"prix": am["prix_neuf_eur"], "marchand": "Amazon.fr", "lien": am.get("lien")})
    if not pistes:
        return None
    r = dict(min(pistes, key=lambda x: x["prix"]))
    if taux and p.get("prix_moyen_usd"):
        r["prix_tiktok_eur"] = round(p["prix_moyen_usd"] * taux, 2)
        r["ecart_eur"] = round(r["prix"] - r["prix_tiktok_eur"], 2)  # positif : c'est plus cher ailleurs que sur TikTok
    return r


def texte_meilleur_prix(p, taux):
    r = meilleur_prix(p, taux)
    if r is None:
        c = p.get("comparaison") or {}
        if c.get("type") == "equivalents":
            return (f"même produit non trouvé ailleurs ; articles du même genre de {_eur(c['min'])} à {_eur(c['max'])} € "
                    f"(médiane {_eur(c['mediane'])} €)")
        return "même produit non trouvé ailleurs"
    debut = f"{_eur(r['prix'])} € chez {r['marchand']} (même produit, neuf)"
    e = r.get("ecart_eur")
    if e is None:
        return debut
    tk = f" ; prix moyen TikTok ≈ {_eur(r['prix_tiktok_eur'])} € : "
    if e > 0.5:
        return debut + tk + f"{_eur(e)} € de plus ailleurs que sur TikTok"
    if e < -0.5:
        return debut + tk + f"{_eur(-e)} € de moins ailleurs que sur TikTok"
    return debut + tk + "même prix"


# ---------- réseau ----------

def taux_usd_eur():
    """Taux du jour de la BCE (gratuit). None si injoignable : on garde alors les dollars seuls."""
    try:
        with urllib.request.urlopen("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=15) as r:
            return float(json.loads(r.read())["rates"]["EUR"])
    except Exception:
        return None


def depense_apify():
    apify._reel.clear()
    return apify.depense_reelle()


def _douteuse(c):
    """Ancienne comparaison sans offres enregistrées dont la fourchette est manifestement faussée par un prix aberrant."""
    return (c.get("type") == "equivalents" and "offres" not in c and c.get("mediane") and c.get("max", 0) > 3 * c["mediane"])


def reserve_restante(reglages, jour=None):
    """Ce qui reste aujourd'hui de la réserve accordée au relevé au-dessus du plafond DataForSEO : « reserve_usd » de
    la config (0,02 $ par jour pour la comparaison de prix le 16/11, porté à 0,04 $ le 19/11/2026 par David pour y
    ajouter le volume de recherche Google)."""
    jour = jour or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with open(F_RESERVE) as source:
            e = json.load(source)
    except (OSError, json.JSONDecodeError):
        e = {}
    pris = float(e.get("pris_usd", 0)) if e.get("jour") == jour else 0.0
    return max(0.0, round(float(reglages.get("reserve_usd", 0)) - pris, 4))


def noter_reserve(cout, jour=None):
    jour = jour or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with open(F_RESERVE) as source:
            e = json.load(source)
    except (OSError, json.JSONDecodeError):
        e = {}
    pris = float(e.get("pris_usd", 0)) if e.get("jour") == jour else 0.0
    os.makedirs(os.path.dirname(F_RESERVE), exist_ok=True)
    with open(F_RESERVE, "w") as cible:
        json.dump({"jour": jour, "pris_usd": round(pris + cout, 4),
                   "note": "Réserve du relevé d'affiliation : comparaison de prix et volumes Google (accords de David des 16/11 et 19/11/2026)."}, cible, indent=1)


def comparer(finalistes, taux, cfg):
    """Une seule demande groupée à Google Shopping (0,002 $ par produit cherché) pour les finalistes pas encore comparés.
    Les offres lues sont enregistrées : si la façon de les trier change, le recalcul est gratuit. Renvoie le nombre de
    comparaisons nouvelles ou recalculées."""
    reglages = cfg.get("comparaison") or {}
    if not reglages.get("actif", True):
        return 0
    demandes, changes = {}, 0
    for p in finalistes:
        c = p.get("comparaison") or {}
        m = marque_fiable(p["titre"])
        q, genre = requete_comparaison(p["titre"], m, reglages.get("mots_min_titre", 6))
        tiktok_eur = p["prix_moyen_usd"] * taux if taux else None
        if "offres" in c and c.get("v") != VERSION_COMPARAISON and q:  # recalcul gratuit
            p["comparaison"] = dict(comparer_offres(c["offres"], p["titre"], m, genre, tiktok_eur), requete=c.get("requete", q), offres=c["offres"])
            changes += 1
        elif c.get("type") in (None, "non_lu") or _douteuse(c):
            if q is None:
                p["comparaison"] = {"type": genre}
            else:
                demandes[id(p)] = (p, q, genre, m, tiktok_eur)
    if not demandes:
        return changes
    cout = shopping.COUT * len({d[1] for d in demandes.values()})
    with dataforseo.reserve(min(reserve_restante(reglages), cout)):  # les passages de nuit ont souvent déjà pris le plafond du jour
        res = sante.protege("affiliation comparaison", shopping.chercher, [d[1] for d in demandes.values()], "FR", defaut={}) or {}
    if res:
        noter_reserve(cout)  # compté même si le plafond normal suffisait : jamais plus de « reserve_usd » par jour
    for p, q, genre, m, tiktok_eur in demandes.values():
        if q not in res:
            if not (p.get("comparaison") or {}).get("type") in ("meme_produit", "equivalents", "aucune"):
                p["comparaison"] = {"type": "non_lu", "requete": q}
            continue
        offres = [{k: o.get(k) for k in ("titre", "prix", "marchand", "lien", "devise")} for o in res[q]]
        p["comparaison"] = dict(comparer_offres(offres, p["titre"], m, genre, tiktok_eur), requete=q, offres=offres)
        changes += 1
    return changes


def demande_google(finalistes, cfg):
    """Volume de recherche mensuel Google France des finalistes (demande de David le 19/11/2026) : UN appel groupé à
    DataForSEO Labs (≈ 0,02 $), pris sur la même réserve du jour que la comparaison de prix. Renvoie le nombre de
    produits lus. Un produit déjà lu n'est jamais redemandé."""
    reglages = cfg.get("google") or {}
    if not reglages.get("actif", True):
        return 0
    a_lire = [p for p in finalistes if not (p.get("google") or {}).get("lu")]
    listes = {id(p): mots_google(p["titre"], marque_fiable(p["titre"]), reglages.get("mots_par_produit", 6)) for p in a_lire}
    demandes = list(dict.fromkeys(m for liste in listes.values() for m, _ in liste))
    if not demandes:
        return 0
    cout = round(0.012 + 0.00012 * len(demandes) + 0.005, 4)  # même calcul que dataforseo.volumes_labs
    with dataforseo.reserve(min(reserve_restante(cfg.get("comparaison") or {}), cout)):
        vols = sante.protege("affiliation google", dataforseo.volumes_labs, demandes, "FR", defaut=None)
    if vols is None:  # budget atteint ou service indisponible : « non lu », réessayé au lancement suivant
        for p in a_lire:
            p["google"] = {"lu": False}
        return 0
    noter_reserve(cout)
    for p in a_lire:
        p["google"] = {"lu": True, "mots": [{"mot": m, "genre": g, "volume": vols.get(m)} for m, g in listes[id(p)]]}
    return len(a_lire)


def enrichir(p, cfg):
    m = marque_fiable(p["titre"])
    p["marque_sure"] = m
    p.update({"ebay": None, "ebay_lu": False, "pubs": None, "pubs_lu": False, "pubs_terme": m, "amazon": None, "recherche": "",
              "amazon_piste": ""})
    if not m:
        return p  # sans marque sûre, aucun recoupement : mieux vaut « non fait » qu'un autre produit
    q = recherche_precise(p["titre"], m)
    p["recherche"] = q
    ventes = apify.lancer("ebay_vendus", {"keywords": [q], "ebaySite": "ebay.fr", "count": cfg["ebay"]["ventes_par_finaliste"],
                                          "daysToScrape": cfg["ebay"]["jours"]}, maxi=cfg["ebay"]["ventes_par_finaliste"])
    p["ebay"] = resume_ebay(garder_ventes(ventes, m))
    p["ebay_lu"] = ventes is not None
    pubs = apify.lancer("pubs", {"mode": "discovery", "searchQuery": [m], "domains": [], "region": cfg["pubs"]["region"],
                                 "includeMeta": True, "includeTikTok": False, "maxItems": cfg["pubs"]["pubs_par_finaliste"],
                                 "rehostMetaMedia": False, "rehostGoogleVideos": False, "rehostTikTokMedia": False,
                                 "includeAdvertiserInfo": False}, maxi=cfg["pubs"]["pubs_par_finaliste"])
    bonnes = garder_pubs(pubs, m)
    p["pubs"] = resume_pubs(bonnes)
    p["pubs_lu"] = pubs is not None
    if cfg.get("keepa"):
        # 1) les fiches amazon.fr vers lesquelles la marque envoie ses propres pubs (1 jeton Keepa par fiche, 4 au plus)
        asins = asins_des_pubs(bonnes)[:4]
        fiches = [sante.protege("affiliation keepa", keepa.fiche, None, a, "FR") for a in asins]
        f = choisir_amazon(p["titre"], fiches, m)
        piste = "fiche Amazon visée par une pub de la marque" if f else ""
        if not f:  # 2) recherche Keepa par nom (10 jetons), gardée seulement si elle ressemble assez
            r = sante.protege("affiliation keepa", keepa.rechercher, q, "FR")
            f = choisir_amazon(p["titre"], [r], m)
            piste = "recherche Keepa par nom" if f else ""
        p["amazon_essais"] = {"fiches_des_pubs": len(asins), "lues": sum(1 for x in fiches if isinstance(x, dict) and not x.get("erreur"))}
        if f:
            p["amazon"] = {"prix_neuf_eur": f.get("prix_neuf"), "asin": f.get("asin"), "titre": f.get("titre"),
                           "rang_ventes": f.get("rang_ventes"), "moyenne_90j": f.get("moyenne_90j"), "lien": f.get("lien")}
            p["amazon_piste"] = piste
    return p


# ---------- rapport ----------

def _usd(v, taux):
    if v is None:
        return "non trouvé"
    s = f"{v:,.2f} $".replace(",", " ").replace(".", ",") if v < 1000 else f"{v:,.0f} $".replace(",", " ")
    return s + (f" (≈ {v * taux:,.2f} €)".replace(",", " ").replace(".", ",") if taux and v < 1000 else "")


def _eur(v):
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _evo(v):
    return "inconnue" if v is None else f"{'+' if v >= 0 else ''}{v:.0f} %"


def _lien_offre(c):
    lien = ((c or {}).get("moins_cher") or {}).get("lien") if isinstance(c, dict) else None
    return f' — <a href="{H.escape(str(lien))}" target="_blank" rel="noopener">voir l\'offre</a>' if lien else ""


def _lien_meilleur(p, taux):
    lien = (meilleur_prix(p, taux) or {}).get("lien")
    return f' — <a href="{H.escape(str(lien))}" target="_blank" rel="noopener">voir l\'offre</a>' if lien else ""


def carte(p, taux):
    e, pb, am = p.get("ebay"), p.get("pubs"), p.get("amazon")
    non_lu = "non lu (budget du jour atteint ou robot indisponible)"
    if not p.get("marque_sure"):
        ebay = pubs = amazon = ("non recoupé : produit sans marque identifiable (risque de confondre avec un autre article)."
                                " À contrôler dans ton appli TikTok : note des acheteurs et échantillon gratuit")
    else:
        if e:
            ebay = (f"{e['nb']} vente(s) de la marque sur 30 jours : de {_eur(e['min'])} à {_eur(e['max'])} {e['devise']}"
                    f" (médiane {_eur(e['mediane'])})")
        else:
            ebay = f"aucune vente trouvée sur ebay.fr pour « {H.escape(p.get('recherche', ''))} »" if p.get("ebay_lu") else non_lu
        if pb:
            pubs = (f"{pb['nb']} pub(s) de la marque « {H.escape(p['pubs_terme'])} »"
                    + (f", la plus ancienne tourne depuis {pb['plus_longue_jours']} jours" if pb["plus_longue_jours"] is not None else "")
                    + (f", {pb['depuis_30j_ou_plus']} depuis 30 jours ou plus" if pb["depuis_30j_ou_plus"] else "")
                    + (f", {pb['vers_amazon']} renvoient vers Amazon" if pb["vers_amazon"] else "")
                    + (f" — annonceurs : {H.escape(', '.join(pb['annonceurs']))}" if pb["annonceurs"] else ""))
        else:
            pubs = f"aucune pub de la marque « {H.escape(p.get('pubs_terme', ''))} » trouvée" if p.get("pubs_lu") else non_lu
        if am:
            amazon = (f"<a href=\"{H.escape(str(am.get('lien') or ''))}\" target=\"_blank\" rel=\"noopener\">{_eur(am['prix_neuf_eur'])} € neuf sur Amazon.fr</a>"
                      + (f" (moyenne sur 90 jours : {_eur(am['moyenne_90j'])} €)" if am.get("moyenne_90j") else "")
                      + f" — {H.escape(str(am.get('titre') or '')[:70])} ; trouvé par : {H.escape(p.get('amazon_piste', ''))}")
        else:
            amazon = f"aucune fiche Amazon.fr assez ressemblante pour « {H.escape(p.get('recherche', ''))} »"
    return f"""<div class="carte"><h3><a href="{H.escape(p['lien'])}" target="_blank" rel="noopener">{H.escape(p['titre'][:110])}</a></h3>
<p class="sig">{'<span class="bingo">BINGO</span> ' if p.get('bingo') else ''}Trouvé par : robot TikTok Shop (Apify), {H.escape(trouve_par(p))} · catégorie {H.escape(p['categorie'] or 'inconnue')} · rang {H.escape(str(p['rang']))}</p>
<table class="kv">
<tr><th>Prix de vente moyen</th><td><b>{_usd(p['prix_moyen_usd'], taux)}</b> sur 7 jours (le prix affiché dans l'appli peut différer : promotions, variantes)</td></tr>
<tr><th>Gain par vente</th><td><b>{_usd(p['gain_par_vente_usd'], taux)}</b> ({p['commission_pct']:g} % de {_usd(p['prix_moyen_usd'], None)})</td></tr>
<tr><th>Ventes sur 7 jours</th><td>{f"{p['ventes_7j']:,}".replace(",", " ")} (évolution {_evo(p['evolution_pct'])})</td></tr>
<tr><th>Commissions totales estimées</th><td>{_usd(p['commissions_totales_usd'], None)} sur 7 jours, tous créateurs confondus</td></tr>
<tr><th>Part des ventes en vidéo</th><td>{'inconnue' if p['part_video_pct'] is None else str(p['part_video_pct']) + ' %'}</td></tr>
<tr><th>Meilleur prix ailleurs</th><td><b>{H.escape(texte_meilleur_prix(p, taux))}</b>{_lien_meilleur(p, taux)}</td></tr>
<tr><th>Recherches Google France</th><td><b>{H.escape(texte_google(p.get('google')) or 'non demandé')}</b></td></tr>
<tr><th>Ailleurs en France</th><td>{H.escape(texte_comparaison(p.get('comparaison')) or 'non comparé')}{_lien_offre(p.get('comparaison'))}</td></tr>
<tr><th>Prix vendus sur eBay.fr</th><td>{ebay}</td></tr>
<tr><th>Publicités en cours</th><td>{pubs}</td></tr>
<tr><th>Prix Amazon.fr</th><td>{amazon}</td></tr>
</table></div>"""


def rapport(tous, finalistes, cfg, taux, cout, quand):
    lignes = []
    liens_finalistes = {f["lien"] for f in finalistes}
    for p in tous:
        ok, raison = retenu(p, cfg["filtres"])
        lignes.append({**{k: p[k] for k in ("titre", "marque", "categorie", "ventes_7j", "prix_moyen_usd", "commission_pct",
                                              "gain_par_vente_usd", "commissions_totales_usd", "evolution_pct", "lien")},
                       "liste": "bingo" if p.get("bingo") else ("en hausse" if "hausses" in (p.get("listes") or []) else "plus vendu"),
                       "etat": "finaliste" if p["lien"] in liens_finalistes else ("retenu" if ok else raison)})
    cout_txt = "non mesuré" if cout is None else f"{cout:.3f} $".replace(".", ",")
    page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Affiliation TikTok Shop</title>
<style>
body{{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1c1f24}}
header{{padding:16px 20px;background:#111;color:#fff}} header p{{margin:4px 0 0;color:#cfd3da;font-size:14px}}
nav{{display:flex;gap:6px;padding:10px 20px;background:#fff;border-bottom:1px solid #dde1e7;position:sticky;top:0}}
nav button{{padding:8px 14px;border:1px solid #c9ced6;background:#fff;border-radius:6px;cursor:pointer;font-size:14px}}
nav button.on{{background:#111;color:#fff;border-color:#111}}
main{{padding:16px 20px;max-width:1200px;margin:auto}} section{{display:none}} section.on{{display:block}}
.carte{{background:#fff;border:1px solid #dde1e7;border-radius:8px;padding:14px 16px;margin:0 0 14px}}
.carte h3{{margin:0 0 4px;font-size:17px}} .sig{{margin:0 0 10px;color:#5b6370;font-size:13px}}
.kv th{{text-align:left;font-weight:500;color:#5b6370;padding:3px 14px 3px 0;vertical-align:top;white-space:nowrap}} .kv td{{padding:3px 0}}
table.liste{{border-collapse:collapse;width:100%;background:#fff;font-size:14px}}
table.liste th,table.liste td{{border-bottom:1px solid #e3e6eb;padding:7px 9px;text-align:left}}
table.liste th{{cursor:pointer;background:#eef0f3;user-select:none;white-space:nowrap}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.filtres{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 12px}} .filtres input,.filtres select{{padding:7px 9px;border:1px solid #c9ced6;border-radius:6px;font-size:14px}}
.bingo{{background:#0a7a3d;color:#fff;border-radius:4px;padding:1px 7px;font-weight:600;font-size:12px}}
.note{{color:#5b6370;font-size:13px}} a{{color:#0b57d0}} .f{{font-weight:600;color:#0a7a3d}}
</style>
<header><h1 style="margin:0;font-size:21px">Affiliation TikTok Shop France</h1>
<p>Relevé du {quand} · {len(tous)} produits lus · {sum(1 for p in tous if p.get('bingo'))} bingo(s) · {len(finalistes)} finaliste(s) · coût Apify de ce lancement : {cout_txt}</p></header>
<nav><button class="on" data-t="fin">Finalistes</button><button data-t="tous">Tous les produits</button><button data-t="lire">Comment lire</button></nav>
<main>
<section id="fin" class="on">{''.join(carte(p, taux) for p in finalistes)}</section>
<section id="tous"><div class="filtres"><input id="q" placeholder="Chercher un produit ou une marque" size="32">
<select id="cat"><option value="">Toutes les catégories</option></select>
<select id="liste"><option value="">Toutes les listes</option><option>bingo</option><option>en hausse</option><option>plus vendu</option></select>
<select id="etat"><option value="">Tous</option><option value="ok">Retenus et finalistes</option><option value="non">Écartés</option></select></div>
<table class="liste"><thead><tr><th data-k="titre">Produit</th><th data-k="liste">Liste</th><th data-k="categorie">Catégorie</th><th data-k="ventes_7j">Ventes 7 j</th>
<th data-k="prix_moyen_usd">Prix moyen ($)</th><th data-k="commission_pct">Commission</th><th data-k="gain_par_vente_usd">Gain par vente ($)</th>
<th data-k="commissions_totales_usd">Commissions totales ($)</th><th data-k="evolution_pct">Évolution</th><th data-k="etat">Verdict</th></tr></thead><tbody id="tb"></tbody></table></section>
<section id="lire"><div class="carte"><h3>Comment lire ce rapport</h3>
<p><b>Liens</b> : ils ouvrent la fiche du produit dans l'appli TikTok. Ouvre le rapport sur ton téléphone ; sur un ordinateur, TikTok n'affiche pas les fiches françaises.</p>
<p><b>Prix de vente moyen</b> : moyenne des ventes des 7 derniers jours, estimée en dollars puis convertie en euros. Ce n'est pas forcément
le prix affiché aujourd'hui dans l'appli (promotions, variantes) : le lien du produit donne le prix exact.</p>
<p><b>Ailleurs en France</b> : prix du neuf chez les marchands français lus sur Google Shopping. « Même produit » = la marque et le type
correspondent. « Produits équivalents » = des articles du même genre, pas forcément le même : c'est une fourchette de marché.
Rien n'est cherché quand le titre est trop vague, pour ne pas comparer avec un autre article.</p>
<p><b>Meilleur prix ailleurs</b> : le prix neuf le plus bas trouvé pour le même produit, chez les marchands français de Google Shopping
ou sur Amazon.fr, comparé au prix moyen TikTok. Si c'est nettement plus cher ailleurs que sur TikTok, il y a peut-être une place pour le
vendre ailleurs ; si c'est moins cher ailleurs, mieux vaut le garder en affiliation. Attention : la taille ou la variante peut différer
(un matelas en 90 ou en 160, un lot de 3 ou de 15 pièces) et les frais de port ne sont pas comptés : ouvre l'offre avant de décider.</p>
<p><b>Recherches Google France</b> : nombre moyen de recherches par mois sur Google en France pour le mot écrit entre guillemets
(estimation DataForSEO). La marque seule ou la marque avec le produit = des gens qui cherchent déjà ce produit hors de TikTok ;
le type de produit seul = la taille du marché, toutes marques confondues. « Aucun volume connu » = trop peu de recherches pour être mesuré.</p>
<p><b>Gain par vente</b> : prix moyen × commission. C'est ce que touche le créateur pour une vente, avant annulation en cas de retour.</p>
<p><b>Commissions totales estimées</b> : revenu estimé × commission, tous créateurs confondus. Cela mesure où se trouve l'argent, pas ce que tu toucheras.</p>
<p><b>Deux classements</b> : « plus vendu » = valeur sûre, déjà très promue ; « en hausse » = ventes qui décollent, moins de créateurs dessus ;
« bingo » = présent dans les deux listes.</p>
<p><b>Finalistes</b> : {cfg['finalistes']} produits au plus, pris à tour de rôle dans trois familles (un bingo, un produit en hausse, un produit très vendu), le plus gros total de commissions d'abord, jamais deux fois la même marque, après avoir écarté les produits réservés aux lives,
les prix moyens sous {cfg['filtres']['prix_moyen_min_usd']} $, les produits à moins de {cfg['filtres']['ventes_min']} ventes ({cfg['filtres'].get('ventes_min_hausses', cfg['filtres']['ventes_min'])} pour la liste des hausses, déjà filtrée sur le chiffre d'affaires), les ventes en recul de plus de {abs(cfg['filtres']['evolution_min_pct'])} % et les gains par vente sous {cfg['filtres']['gain_par_vente_min_usd']} $.</p>
<p class="note">Les ventes et revenus TikTok sont des estimations du fournisseur de données, en dollars : ils servent à comparer les produits entre eux.
Le taux de commission est celui annoncé par le robot ; vérifie-le dans ton catalogue créateur avant de tourner la vidéo.
{'Conversion en euros au taux BCE du jour : 1 $ = ' + format(taux, '.4f').replace('.', ',') + ' €.' if taux else 'Conversion en euros indisponible aujourd’hui : montants en dollars seuls.'}</p></div></section>
</main>
<script>
const D={json.dumps(lignes, ensure_ascii=False).replace("</", "<\\/")};
let tri="commissions_totales_usd",sens=-1;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));
const fr=(v,d)=>v==null?"inconnue":Number(v).toLocaleString("fr-FR",{{minimumFractionDigits:d,maximumFractionDigits:d}});
const cats=[...new Set(D.map(x=>x.categorie).filter(Boolean))].sort();
document.getElementById("cat").innerHTML+=cats.map(c=>`<option>${{esc(c)}}</option>`).join("");
function dessiner(){{
  const q=document.getElementById("q").value.toLowerCase(),c=document.getElementById("cat").value,e=document.getElementById("etat").value,li=document.getElementById("liste").value;
  const ok=x=>x.etat==="finaliste"||x.etat==="retenu";
  const L=D.filter(x=>(!q||(x.titre+" "+x.marque).toLowerCase().includes(q))&&(!c||x.categorie===c)&&(!li||x.liste===li)&&(!e||(e==="ok")===ok(x)));
  L.sort((a,b)=>{{const x=a[tri],y=b[tri];if(x==null)return 1;if(y==null)return -1;return (typeof x==="number"?x-y:String(x).localeCompare(String(y),"fr"))*sens}});
  document.getElementById("tb").innerHTML=L.map(x=>`<tr><td><a href="${{esc(x.lien)}}" target="_blank" rel="noopener">${{esc(x.titre.slice(0,80))}}</a></td><td class="${{x.liste==="bingo"?"f":""}}">${{esc(x.liste)}}</td><td>${{esc(x.categorie)}}</td>
<td class="n">${{fr(x.ventes_7j,0)}}</td><td class="n">${{fr(x.prix_moyen_usd,2)}}</td><td class="n">${{fr(x.commission_pct,0)}} %</td><td class="n">${{fr(x.gain_par_vente_usd,2)}}</td>
<td class="n">${{fr(x.commissions_totales_usd,0)}}</td><td class="n">${{x.evolution_pct==null?"inconnue":(x.evolution_pct>=0?"+":"")+fr(x.evolution_pct,0)+" %"}}</td>
<td class="${{ok(x)?"f":""}}">${{esc(x.etat)}}</td></tr>`).join("");
}}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{{document.querySelectorAll("nav button,section").forEach(x=>x.classList.remove("on"));b.classList.add("on");document.getElementById(b.dataset.t).classList.add("on")}});
document.querySelectorAll("th[data-k]").forEach(t=>t.onclick=()=>{{sens=tri===t.dataset.k?-sens:-1;tri=t.dataset.k;dessiner()}});
["q","cat","etat","liste"].forEach(i=>document.getElementById(i).oninput=dessiner);
dessiner();
</script></html>"""
    with open(F_HTML, "w", encoding="utf-8") as f:
        f.write(page)


def message_telegram(finalistes, taux, n_lus):
    blocs = [f"<b>Affiliation TikTok Shop</b> — {n_lus} produits lus, {len(finalistes)} à tester en vidéo :"]
    for i, p in enumerate(finalistes, 1):
        e, pb = p.get("ebay"), p.get("pubs")
        etiquette = "BINGO" if p.get("bingo") else ("en hausse" if "hausses" in (p.get("listes") or []) else "plus vendu")
        blocs.append(f"\n{i}. [{etiquette}] <a href=\"{H.escape(p['lien'])}\">{H.escape(p['titre'][:70])}</a>\n"
                     f"Prix de vente moyen : {_usd(p['prix_moyen_usd'], taux)}\n"
                     f"Gain par vente : {_usd(p['gain_par_vente_usd'], taux)} ({p['commission_pct']:g} %) · {p['ventes_7j']} ventes sur 7 j ({_evo(p['evolution_pct'])})\n"
                     + ("" if p.get("marque_sure") else "Recoupement eBay, Amazon et pubs non fait : pas de marque identifiable\n")
                     + (f"Ailleurs en France : {H.escape(texte_comparaison(p.get('comparaison')))}\n"
                        if (p.get("comparaison") or {}).get("type") in ("meme_produit", "equivalents") else "")
                     + (f"Meilleur prix ailleurs : {H.escape(texte_meilleur_prix(p, taux))}\n" if meilleur_prix(p, taux) else "")
                     + (f"Recherches Google France : {H.escape(texte_google(p.get('google')))}\n"
                        if any(isinstance(x.get("volume"), int) for x in (p.get("google") or {}).get("mots") or []) else "")
                     + (f"Amazon.fr : {_eur(p['amazon']['prix_neuf_eur'])} € neuf\n" if p.get("amazon") else "")
                     + (f"eBay.fr : {e['nb']} vente(s), médiane {_eur(e['mediane'])} {e['devise']}\n" if e else "")
                     + (f"Pubs de la marque : {pb['nb']}" + (f", la plus ancienne depuis {pb['plus_longue_jours']} j" if pb['plus_longue_jours'] is not None else "") + "\n" if pb else ""))
    return "".join(blocs)


CLES = ("titre", "marque", "categorie", "rang", "ventes_7j", "prix_moyen_usd", "commission_pct", "gain_par_vente_usd",
        "revenu_usd", "commissions_totales_usd", "part_video_pct", "evolution_pct", "lien")


def reglage(cfg, c):
    """Ce qui définit un classement : s'il change, le classement déjà lu aujourd'hui n'est plus valable."""
    return {"tri": c["tri"], "revenu_min_usd": c.get("revenu_min_usd", 0), "categories": cfg["categories"],
            "produits_par_categorie": cfg["produits_par_categorie"], "pays": cfg["pays"], "periode": cfg["periode"]}


VERSION_RAPPORT = 6    # à augmenter quand la présentation change : le rapport du jour est alors refait, sans rien repayer
METHODE_SELECTION = 2  # à augmenter quand la façon de choisir les finalistes change


def reglage_selection(cfg):
    return {"methode": METHODE_SELECTION, "finalistes": cfg["finalistes"], "filtres": cfg["filtres"]}


def deja_lus(ancien, jour, nom, attendu=None):
    """Produits d'un classement déjà payé aujourd'hui avec les mêmes réglages (ou None)."""
    if not isinstance(ancien, dict):
        return None
    if ancien.get("jour") == jour and (ancien.get("classements") or {}).get(nom):
        connu = (ancien.get("reglages") or {}).get(nom)
        if attendu is None or connu == attendu or (connu is None and nom == "plus_vendus"):
            return ancien["classements"][nom]
        return None
    if nom == "plus_vendus" and "classements" not in ancien and str(ancien.get("quand", "")).startswith(jour) and ancien.get("tous"):
        return ancien["tous"]  # ancien format (premier relevé du 15/11/2026)
    return None


def main():
    cfg = json.load(open(F_CONFIG, encoding="utf-8"))
    apify.CONTEXTE["denicheur"] = "T"
    jour = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y")
    try:
        ancien = json.load(open(F_JSON, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        ancien = None
    noms = [c["nom"] for c in cfg["classements"]]
    if (isinstance(ancien, dict) and ancien.get("jour") == jour and ancien.get("finalistes")
            and all(deja_lus(ancien, jour, c["nom"], reglage(cfg, c)) for c in cfg["classements"])
            and ancien.get("selection") == reglage_selection(cfg)
            and os.environ.get("AFFIL_FORCER") != "1"):
        print(f"Relevé du {jour} déjà complet : rien n'est relancé ni repayé (AFFIL_FORCER=1 pour forcer).")
        a_comparer = any((f.get("comparaison") or {}).get("type") in (None, "non_lu") for f in ancien["finalistes"])
        compares = comparer(ancien["finalistes"], ancien.get("taux_usd_eur"), cfg) if a_comparer else 0
        compares += demande_google(ancien["finalistes"], cfg)  # ne demande que les finalistes sans volume Google
        if ancien.get("rapport_version") != VERSION_RAPPORT or compares:  # page refaite sans repayer les classements
            for liste in [ancien["tous"], ancien["finalistes"]] + list(ancien["classements"].values()):
                for p in liste:
                    p["lien"] = lien_appli(p.get("lien"))
            ancien["rapport_version"] = VERSION_RAPPORT
            rapport(ancien["tous"], ancien["finalistes"], cfg, ancien.get("taux_usd_eur"), ancien.get("cout_apify_mesure_usd"), ancien["quand"])
            with open(F_JSON, "w", encoding="utf-8") as f:
                json.dump(ancien, f, ensure_ascii=False, indent=1)
            telegram.envoyer("Rapport mis à jour : meilleur prix ailleurs et recherches Google France.\n\n"
                             + message_telegram(ancien["finalistes"], ancien.get("taux_usd_eur"), len(ancien["tous"])))
            telegram.envoyer_fichier(F_HTML, "Affiliation TikTok Shop : rapport mis à jour")
            print(f"Rapport du jour refait ; {compares} lecture(s) nouvelle(s) (Google Shopping, volumes Google).")
            for f in ancien["finalistes"]:
                print(" -", f["titre"][:50], "| ailleurs", {k: v for k, v in (f.get("comparaison") or {}).items() if k != "offres"},
                      "| google", f.get("google"))
        return 0
    avant = depense_apify()
    n = len(cfg["categories"]) * cfg["produits_par_categorie"]
    classements, repris = {}, []
    for c in cfg["classements"]:
        deja = deja_lus(ancien, jour, c["nom"], reglage(cfg, c)) if cfg.get("reutiliser_classement_du_jour", True) else None
        if deja:
            repris.append(c["nom"])
            produits = []
            for p in deja:
                p = {k: p.get(k) for k in CLES}
                p["categorie"] = categorie_principale(p["categorie"])
                p["lien"] = lien_appli(p["lien"])
                produits.append(p)
        else:
            entree = {"country": cfg["pays"], "period": cfg["periode"], "sortBy": c["tri"], "categories": cfg["categories"],
                      "maxResultsPerSource": cfg["produits_par_categorie"], "addAnalytics": False}
            if c.get("revenu_min_usd"):
                entree["minRevenue"] = int(c["revenu_min_usd"])  # sans ce plancher, les « hausses » sont des produits à 10 ventes
            brut = apify.lancer("tiktok_top", entree, maxi=n + len(cfg["categories"]))
            if brut is None:
                sante.noter("erreur", "affiliation tiktok", f"classement « {c['nom']} » non lu (budget du jour ou du mois atteint, jeton absent, ou robot en erreur)")
                print(f"Classement {c['nom']} non lu.")
                continue
            vus, produits = set(), []
            for ligne in brut:
                p = lire_produit(ligne)
                if p and p["lien"] not in vus:
                    vus.add(p["lien"])
                    produits.append(p)
        classements[c["nom"]] = produits
        print(f"classement {c['nom']} : {len(produits)} produits" + (" (repris du relevé du jour)" if deja else ""))
    tous = fusionner(classements)
    if not tous:
        sante.noter("erreur", "affiliation tiktok", "aucun produit lisible dans les classements")
        print("Aucun produit lisible : aucun rapport écrit.")
        return 1
    complet = len(classements) == len(noms)
    finalistes = choisir_finalistes(tous, cfg["filtres"], cfg["finalistes"]) if complet else []
    taux = taux_usd_eur()
    for p in finalistes:  # aucun recoupement payant tant qu'un classement manque
        sante.protege("affiliation enrichir", enrichir, p, cfg)
    if finalistes:
        sante.protege("affiliation comparaison", comparer, finalistes, taux, cfg)
        sante.protege("affiliation google", demande_google, finalistes, cfg)
    apres = depense_apify()
    cout = round(apres - avant, 4) if avant is not None and apres is not None else None
    quand = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y à %H h %M")
    par_cat = {}
    for p in tous:
        par_cat[p["categorie"]] = par_cat.get(p["categorie"], 0) + 1
    with open(F_JSON, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "rapport_version": VERSION_RAPPORT, "jour": jour, "quand": quand, "classements_repris": repris, "taux_usd_eur": taux,
                   "cout_apify_mesure_usd": cout, "selection": reglage_selection(cfg),
                   "reglages": {c["nom"]: (ancien or {}).get("reglages", {}).get(c["nom"]) if c["nom"] in repris else reglage(cfg, c)
                                for c in cfg["classements"] if c["nom"] in classements},
                   "produits_par_categorie": par_cat, "bingos": sum(1 for p in tous if p["bingo"]),
                   "finalistes": finalistes, "classements": {k: [{c: p.get(c) for c in CLES} for p in v] for k, v in classements.items()},
                   "tous": tous}, f, ensure_ascii=False, indent=1)
    print(f"{len(tous)} produits uniques {par_cat} ; {sum(1 for p in tous if p['bingo'])} bingo(s) ; {len(finalistes)} finaliste(s) ; coût Apify mesuré : {cout}")
    for p in finalistes:
        print(" -", "BINGO" if p["bingo"] else p["listes"], p["titre"][:60], "| marque sûre", repr(p.get("marque_sure")), "| recherche", repr(p.get("recherche")),
              "| gain/vente", p["gain_par_vente_usd"], "$ | ventes", p["ventes_7j"], "| évolution", p["evolution_pct"],
              "| eBay", p.get("ebay"), "| pubs", p.get("pubs"), "| Amazon", p.get("amazon"),
              "| ailleurs", {k: v for k, v in (p.get("comparaison") or {}).items() if k != "offres"}, "| google", p.get("google"))
    if not complet:
        print("Un classement manque : données enregistrées, aucun rapport envoyé (il sera complété au prochain lancement).")
        return 1
    if not finalistes:
        sante.noter("erreur", "affiliation tiktok", f"{len(tous)} produits lus mais aucun ne passe les filtres")
        print("Aucun finaliste : données enregistrées, aucun rapport envoyé.")
        return 1
    rapport(tous, finalistes, cfg, taux, cout, quand)
    telegram.envoyer(message_telegram(finalistes, taux, len(tous)))
    telegram.envoyer_fichier(F_HTML, "Affiliation TikTok Shop : rapport complet (onglets, tri, filtres)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
