"""PRIX DES PLUS RECHERCHÉS ET DE LA HYPE (Keepa, abonnement déjà payé, aucun coût en plus).
- Les 10 recherches idealo les plus populaires de chaque pays : moins cher, plus cher et meilleure vente sur Amazon,
  avec le prix de la meilleure vente en France, Allemagne, Italie, Espagne (≈ 13 jetons par recherche, revue tous les 3 jours).
- Hype USA/Japon absente ou mal vendue en France : prix du même produit sur Amazon Allemagne, Italie, Espagne
  (3 jetons par produit, revue tous les 7 jours).
-> data/recherches_prix.json        à chaque tour de moisson, ou d'un coup : outils/recherches_prix_jour.py"""
import json
import os
import statistics
from datetime import datetime, timedelta, timezone

from . import comparateurs, moisson

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_PRIX = os.path.join(RACINE, "data/recherches_prix.json")
PAYS = ("FR", "DE", "IT", "ES")
SITE = {"FR": "fr", "DE": "de", "IT": "it", "ES": "es"}
TOP = 10
JOURS_RECHERCHE, JOURS_HYPE = 3, 7
COUT_RECHERCHE = 13


def _lire(f, defaut):
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaut


def _ecrire(d):
    d["maj"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    with open(F_PRIX, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0)


def _limite(jours):
    return (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%d")


def _aujourdhui():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def lien(asin, pays):
    return f"https://www.amazon.{SITE[pays]}/dp/{asin}"


def a_faire():
    """Les TOP recherches de chaque pays, la plus populaire d'abord."""
    d = _lire(os.path.join(RACINE, "data/demande.json"), {})
    par_pays = {}
    for x in d.get("liste", []):
        if x.get("pays") in PAYS and x.get("recherche"):
            par_pays.setdefault(x["pays"], []).append(x)
    out = []
    for p, liste in par_pays.items():
        liste.sort(key=lambda x: -(x.get("popularite") or 0))
        out += [(x.get("popularite") or 0, x["recherche"], p) for x in liste[:TOP]]
    out.sort(key=lambda t: -t[0])
    return [(q, p) for _, q, p in out]


def analyser(q, pays):
    """Recherche Keepa sur l'Amazon du pays : garde les vrais résultats (pas les accessoires bon marché)."""
    d = moisson._appel("search", {"domain": moisson.DOMAINES.get(pays, 4), "type": "product", "term": q[:100], "stats": 180, "history": 0})
    res = []
    for p in (d.get("products") or [])[:10]:
        if isinstance(p, dict):
            r = moisson.resumer(p, pays)
            if r.get("neuf") and comparateurs.correspond(r.get("t") or "", q):
                res.append(r)
    if not res:
        return {"pays": pays, "jour": _aujourdhui(), "nb": 0}
    mediane = statistics.median(r["neuf"] for r in res)
    bons = [r for r in res if r["neuf"] >= mediane * 0.35]
    fiche = lambda r: {"titre": r.get("t"), "prix": r["neuf"], "asin": r["asin"], "lien": lien(r["asin"], pays),
                       "ventes_30j": r.get("ch30"), "vendeurs": r.get("offres")}
    bas, haut = min(bons, key=lambda r: r["neuf"]), max(bons, key=lambda r: r["neuf"])
    top = max(bons, key=lambda r: r.get("ch30") or 0)
    par_pays = {pays: {"prix": top["neuf"], "lien": lien(top["asin"], pays)}}
    for p in PAYS:
        if p != pays:
            for r in moisson.fiches([top["asin"]], p):
                if r.get("neuf"):
                    par_pays[p] = {"prix": r["neuf"], "lien": lien(top["asin"], p)}
    return {"pays": pays, "jour": _aujourdhui(), "nb": len(bons), "moins_cher": fiche(bas), "plus_cher": fiche(haut),
            "meilleure_vente": fiche(top), "par_pays": par_pays}


def prix_europe(asins):
    """Prix du même produit sur Amazon Allemagne, Italie, Espagne (1 jeton par produit et par pays)."""
    out = {a: {"jour": _aujourdhui()} for a in asins}
    for p in ("DE", "IT", "ES"):
        for i in range(0, len(asins), 100):
            for r in moisson.fiches(asins[i:i + 100], p):
                if r.get("neuf"):
                    out[r["asin"]][p] = r["neuf"]
    return out


def hype_a_faire(connus):
    h = _lire(moisson.F_HYPE, {}).get("produits", [])
    limite = _limite(JOURS_HYPE)
    h = [x for x in h if (connus.get(x["asin"]) or {}).get("jour", "") < limite]
    h.sort(key=lambda x: -(x.get("ventes_30j_labas") or 0))
    return list(dict.fromkeys(x["asin"] for x in h))


def tour(etat, maxi=3, maxi_hype=30):
    """Une récolte dans les jetons restants. Renvoie le nombre de recherches et de produits mis à jour."""
    d = _lire(F_PRIX, {"recherches": {}, "hype": {}})
    limite, n = _limite(JOURS_RECHERCHE), 0
    for q, pays in a_faire():
        if n >= maxi or not moisson._peut(COUT_RECHERCHE, etat):
            break
        if (d["recherches"].get(q.lower()) or {}).get("jour", "") >= limite:
            continue
        d["recherches"][q.lower()] = analyser(q, pays)
        n += 1
    asins = hype_a_faire(d["hype"])[:maxi_hype]
    if asins and moisson._peut(len(asins) * 3, etat):
        d["hype"].update(prix_europe(asins))
    else:
        asins = []
    if n or asins:
        _ecrire(d)
    return n + len(asins)
