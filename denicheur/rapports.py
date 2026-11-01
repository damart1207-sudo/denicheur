"""Rapports « Demande » et « Concurrence » pour chaque affaire (outils gratuits).

Concurrence : API officielle eBay (gratuite) dans 4 pays -> nombre d'annonces neuves en cours,
              l'annonce la moins chère et la plus chère (avec lien), niveau peu / moyen / nombreux.
Demande     : Google Trends (intérêt relatif 0-100 sur 90 jours en France, tendance, recherches liées)
              + suggestions Google (ce que les gens tapent) + température Dealabs.
              Pas de volume exact type Semrush : ce chiffre n'existe que dans des outils payants.
"""
import json
import re
import urllib.parse
import urllib.request

from . import ebay

MARCHES = {"FR": "EBAY_FR", "DE": "EBAY_DE", "IT": "EBAY_IT", "ES": "EBAY_ES"}


def _annonces(tok, q, marche, mini, maxi, limite=200, tri="price"):
    params = urllib.parse.urlencode({"q": q, "limit": limite, "sort": tri,
                                     "filter": f"buyingOptions:{{FIXED_PRICE}},conditionIds:{{1000}},priceCurrency:EUR,price:[{mini:.0f}..{maxi:.0f}]"})
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


ACCESSOIRES = re.compile(r"bracelet|sangle|strap|band\b|armband|cinturino|correa|coque|h[uü]lle|case\b|cover|funda|custodia|chargeur|charger|ladekabel|cargador|caricatore|c[aâ]ble|kabel|cable|film|protect|schutz|glas\b|verre|pellicola|protector|support|halter|soporte|supporto|t-?shirt|maglia|camis|shirt|top\b|tee\b|chaussettes|socken|lacets|schn[uü]rsenkel|semelle|insole|sticker|autocollant|pi[eè]ce|ersatz|repuesto|ricambio|bo[iî]te vide|leerkarton|\bGS\b|enfant|kinder|junior|bambino|ni[nñ]o|\bPS\b|\bTD\b", re.I)


def _garder(items, q):
    mots = [m.lower() for m in re.findall(r"\w+", q) if len(m) > 1]
    return [i for i in items if i["titre"] and all(m in i["titre"].lower() for m in mots)
            and not ACCESSOIRES.search(i["titre"])]


def niveau(nb):
    return "peu" if nb < 10 else ("moyen" if nb <= 50 else "nombreux")


def concurrence(tok, q, prix_achat):
    rapport = {"requete": q, "pays": {}}
    for code, marche in MARCHES.items():
        try:
            total, bas = _annonces(tok, q, marche, prix_achat * 0.5, prix_achat * 4)
            bas_ok = _garder(bas, q)
            haut_ok = _garder(_annonces(tok, q, marche, prix_achat * 0.5, prix_achat * 4, tri="-price")[1], q) if total > len(bas) else []
        except Exception as e:
            rapport["pays"][code] = {"erreur": f"{type(e).__name__}"}
            continue
        # nombre estimé de vraies annonces du produit (part des annonces gardées x total eBay)
        nb = round(total * len(bas_ok) / len(bas)) if bas else 0
        tous = sorted(bas_ok + haut_ok, key=lambda i: i["prix"])
        rapport["pays"][code] = {
            "nb_annonces": nb, "total_ebay": total, "niveau": niveau(nb),
            "moins_cher": tous[0] if tous else None, "plus_cher": tous[-1] if tous else None}
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
