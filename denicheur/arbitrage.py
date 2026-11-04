"""ARBITRAGE EUROPE (Amigo + moissonneur) : le même produit coûte souvent 15 à 30 % de moins sur Amazon Allemagne,
Italie ou Espagne qu'en France. Keepa compare chaque produit de NOTRE base sur les 4 pays (1 jeton par produit et par pays,
100 produits par appel), à chaque tour de veille, en continu. Personne n'attend un forum : l'écart est calculé.

Carte quand : écart ≥ ECART_MIN après port (PORT_EUR) ; le produit se vend en France (ventes 30 j ≥ VENTES_MIN) ;
≤ VENDEURS_MAX vendeurs neufs sur Amazon.fr ; prix France entre PRIX_MIN et PRIX_MAX.
-> data/arbitrage.json (meilleurs écarts) ; annonces_arbitrage() les donne au passage comme n'importe quelle annonce.
python -m denicheur.arbitrage   (un tour à la main)"""
import json
import os
from datetime import datetime, timedelta, timezone

from . import moisson, sante

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_ARB = os.path.join(RACINE, "data/arbitrage.json")
F_VUS = os.path.join(RACINE, "data/etat/arbitrage_vus.json")
PAYS = ("DE", "IT", "ES")
PORT_EUR = 7.0          # livraison Amazon DE/IT/ES -> France (ordre de grandeur, souvent gratuite dès 39-59 €)
ECART_MIN = 0.15        # au moins 15 % moins cher à l'étranger, port compris
VENTES_MIN = 3          # chutes de classement sur 30 jours en France (≈ ventes)
VENDEURS_MAX = 9
PRIX_MIN, PRIX_MAX = 25.0, 600.0
PAR_TOUR = 40           # produits comparés par tour (x 4 pays = 160 jetons) : ≈ 4 800 produits par jour
REVOIR_JOURS = 3        # un produit est recomparé au plus tous les 3 jours


def _lire(f, defaut):
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaut


def _ecrire(f, d):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def file_attente(vus):
    """ASIN de la base (fiches FR qui se vendent), les plus vendus d'abord, pas revus depuis REVOIR_JOURS."""
    idx = _lire(moisson.F_INDEX, {})
    limite = (datetime.now(timezone.utc) - timedelta(days=REVOIR_JOURS)).strftime("%Y-%m-%d")
    cands = []
    for k, r in idx.items():
        if not k.endswith(":FR"):
            continue
        asin = k.split(":")[0]
        if (r.get("ch30") or 0) < VENTES_MIN or not r.get("neuf") or not (PRIX_MIN <= r["neuf"] <= PRIX_MAX):
            continue
        if (vus.get(asin) or "") >= limite:
            continue
        cands.append((r.get("ch30") or 0, asin))
    cands.sort(reverse=True)
    # d'abord les baisses de prix vues en Allemagne / Italie / Espagne par le radar (file prioritaire), pas encore comparées
    prio = [a for a in _lire(moisson.F_PRIORITE, []) if (vus.get(a) or "") < limite]
    return list(dict.fromkeys(prio + [a for _, a in cands]))


def comparer(asins):
    """Fiches FR + DE/IT/ES (résumés), et lignes d'arbitrage pour les écarts qui valent le coup."""
    fr = {r["asin"]: r for r in moisson.fiches(asins, "FR")}
    etranger = {p: {r["asin"]: r for r in moisson.fiches(asins, p)} for p in PAYS}
    lignes = []
    for asin in asins:
        f = fr.get(asin)
        if not f or not f.get("neuf") or (f.get("ch30") or 0) < VENTES_MIN or (f.get("offres") or 0) > VENDEURS_MAX:
            continue
        for p in PAYS:
            e = etranger[p].get(asin)
            if not e or not e.get("neuf"):
                continue
            cout = round(e["neuf"] + PORT_EUR, 2)
            ecart = round(1 - cout / f["neuf"], 3)
            if ecart < ECART_MIN:
                continue
            lignes.append({"asin": asin, "ean": f.get("ean"), "titre": f.get("t"), "marque": f.get("marque"), "pays_achat": p,
                           "prix_achat": e["neuf"], "cout_rendu": cout, "prix_fr": f["neuf"], "moyenne_90j_fr": f.get("m90"),
                           "ecart_pct": round(ecart * 100), "ventes_30j_fr": f.get("ch30"), "vendeurs_fr": f.get("offres"),
                           "rang_fr": f.get("rang"), "lien_achat": f"https://www.amazon.{ {'DE': 'de', 'IT': 'it', 'ES': 'es'}[p] }/dp/{asin}",
                           "lien_fr": f"https://www.amazon.fr/dp/{asin}", "vu": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")})
    # une ligne par produit : le pays le moins cher
    meilleur = {}
    for l in lignes:
        if l["asin"] not in meilleur or l["cout_rendu"] < meilleur[l["asin"]]["cout_rendu"]:
            meilleur[l["asin"]] = l
    return list(fr.values()) + [r for p in PAYS for r in etranger[p].values()], list(meilleur.values())


def tour(etat=None, par_tour=PAR_TOUR):
    """Un tour : PAR_TOUR produits comparés sur 4 pays. Renvoie le nombre d'écarts trouvés."""
    if etat is not None and not moisson._peut(par_tour * 4 + 5, etat):
        return 0
    vus = _lire(F_VUS, {})
    asins = file_attente(vus)[:par_tour]
    if not asins:
        return 0
    try:
        resumes, lignes = comparer(asins)
    except Exception as ex:
        sante.noter("erreur", "arbitrage", f"{type(ex).__name__}: {str(ex)[:120]}")
        return 0
    moisson._garder(resumes)
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for a in asins:
        vus[a] = jour
    _ecrire(F_VUS, {k: v for k, v in vus.items() if v >= (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")})
    d = _lire(F_ARB, {"ecarts": []})
    deja = {l["asin"] for l in lignes}
    limite = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    anciens = [l for l in d.get("ecarts", []) if l["asin"] not in deja and (l.get("vu") or "") >= limite]
    tout = sorted(anciens + lignes, key=lambda l: -(l["ecart_pct"] * (1 + min(l.get("ventes_30j_fr") or 0, 50) / 25)))[:500]
    d = {"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "compares_total": len(vus), "nb": len(tout), "ecarts": tout}
    _ecrire(F_ARB, d)
    return len(lignes)


def annonces_arbitrage(maxi=80):
    """Les écarts au format annonce, pour le passage : achat sur Amazon DE/IT/ES, prix France connu."""
    out = []
    for l in _lire(F_ARB, {}).get("ecarts", [])[:maxi]:
        out.append({"id": f'keepa-{l["asin"]}-arb{l["pays_achat"]}', "titre": (l.get("titre") or "") + f' [Amazon {l["pays_achat"]}]',
                    "temperature": min(int(l["ecart_pct"] * 10), 900), "categorie": "Arbitrage Europe", "marchand": f'Amazon.{ {"DE": "de", "IT": "it", "ES": "es"}[l["pays_achat"]] }',
                    "prix": l["prix_achat"], "devise": "EUR", "lien": l["lien_achat"], "date": l.get("vu", ""), "source": "keepa-arbitrage",
                    "pays": l["pays_achat"], "ean": l.get("ean"), "asin": l["asin"], "ref_fr": l["prix_fr"],
                    "ventes_30j": l.get("ventes_30j_fr"), "vendeurs": l.get("vendeurs_fr"),
                    "description": f'Amazon.fr {l["prix_fr"]} € (moyenne 90 j {l.get("moyenne_90j_fr")} €), écart {l["ecart_pct"]} % port compris, '
                                   f'ventes 30 j {l.get("ventes_30j_fr")}, {l.get("vendeurs_fr")} vendeurs FR'})
    return out


if __name__ == "__main__":
    print("écarts trouvés :", tour())
