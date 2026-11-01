"""Rapports « Demande » et « Concurrence » pour chaque affaire (outils gratuits).

Concurrence : API officielle eBay (gratuite) dans 4 pays -> nombre d'annonces neuves en cours,
              l'annonce la moins chère et la plus chère (avec lien), niveau peu / moyen / nombreux.
Demande     : Google Trends (intérêt relatif 0-100 sur 90 jours en France, tendance, recherches liées)
              + suggestions Google (ce que les gens tapent) + température Dealabs.
              Pas de volume exact type Semrush : ce chiffre n'existe que dans des outils payants.
"""
import json
import urllib.parse
import urllib.request

from . import ebay

MARCHES = {"FR": "EBAY_FR", "DE": "EBAY_DE", "IT": "EBAY_IT", "ES": "EBAY_ES"}


def _annonces(tok, q, marche, limite=200):
    params = urllib.parse.urlencode({"q": q, "limit": limite, "sort": "price",
                                     "filter": "buyingOptions:{FIXED_PRICE},conditionIds:{1000},priceCurrency:EUR"})
    req = urllib.request.Request(f"{ebay.SEARCH_URL}?{params}", headers={
        "Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": marche,
        "Accept-Language": ebay.LANGUES.get(marche, "en-GB")})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    items = []
    for it in d.get("itemSummaries", []):
        try:
            items.append({"prix": float(it["price"]["value"]), "titre": it.get("title"), "lien": it.get("itemWebUrl"),
                          "vendeur": (it.get("seller") or {}).get("username"),
                          "avis_vendeur": (it.get("seller") or {}).get("feedbackScore")})
        except (KeyError, TypeError, ValueError):
            continue
    return d.get("total", len(items)), items


def niveau(nb):
    return "peu" if nb < 10 else ("moyen" if nb <= 50 else "nombreux")


def concurrence(tok, q, prix_achat):
    rapport = {"requete": q, "pays": {}}
    for code, marche in MARCHES.items():
        try:
            total, items = _annonces(tok, q, marche)
        except Exception as e:
            rapport["pays"][code] = {"erreur": f"{type(e).__name__}"}
            continue
        utiles = [i for i in items if i["prix"] >= prix_achat * 0.6]  # écarte accessoires et pièces
        utiles.sort(key=lambda i: i["prix"])
        rapport["pays"][code] = {
            "nb_annonces": len(utiles), "total_ebay": total, "niveau": niveau(len(utiles)),
            "moins_cher": utiles[0] if utiles else None, "plus_cher": utiles[-1] if utiles else None}
    nbs = [p["nb_annonces"] for p in rapport["pays"].values() if "nb_annonces" in p]
    rapport["niveau_global"] = niveau(max(nbs)) if nbs else None
    return rapport


def suggestions(q):
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode(
        {"client": "firefox", "hl": "fr", "gl": "fr", "q": q})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))[1][:10]


def tendances(q):
    from pytrends.request import TrendReq
    t = TrendReq(hl="fr-FR", tz=-60, timeout=(10, 25), retries=1, backoff_factor=2)
    t.build_payload([q], timeframe="today 3-m", geo="FR")
    df = t.interest_over_time()
    if df.empty:
        return {"interet_moyen": 0, "tendance": "aucune recherche mesurable"}
    s = df[q].tolist()
    recent, avant = sum(s[-4:]) / 4, (sum(s[-8:-4]) / 4 or 1)
    res = {"interet_moyen": round(sum(s) / len(s)), "interet_recent": round(recent),
           "tendance": "en hausse" if recent > avant * 1.15 else ("en baisse" if recent < avant * 0.85 else "stable"),
           "courbe": [round(x) for x in s]}
    try:
        lies = t.related_queries().get(q, {}).get("top")
        res["recherches_liees"] = lies.head(8).to_dict("records") if lies is not None else []
    except Exception:
        res["recherches_liees"] = []
    return res


def demande(q, temperature=None):
    rapport = {"requete": q, "temperature_dealabs": temperature}
    for nom, f in (("google_trends", tendances), ("suggestions_google", suggestions)):
        try:
            rapport[nom] = f(q)
        except Exception as e:
            rapport[nom] = {"erreur": f"{type(e).__name__}: {str(e)[:120]}"}
    return rapport
