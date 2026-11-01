"""Prix réels des annonces eBay (API officielle Browse, gratuite) pour contrôler le prix de revente.

Les clés viennent des secrets GitHub EBAY_CLIENT_ID et EBAY_CLIENT_SECRET (clés Production).
L'API Browse donne les annonces EN COURS (prix demandés), pas les ventes conclues : on retient donc
une valeur prudente (le premier quart des prix), jamais la moyenne.
"""
import base64
import json
import os
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
MOTS_VIDES = re.compile(r"\[.*?\]|\(.*?\)|via .*$|\b(bei|chez|sur|at|en|de|la|le|les|pour|für|mit|avec|offert|gratis|gratuit|livraison|tailles?|talla|taille)\b", re.I)


def jeton(client_id=None, secret=None):
    client_id = client_id or os.environ.get("EBAY_CLIENT_ID", "").strip()
    secret = secret or os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        raise RuntimeError("clés eBay absentes (EBAY_CLIENT_ID / EBAY_CLIENT_SECRET)")
    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, headers={
        "Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def requete(titre, mots=7):
    t = re.split(r"\s[-–|:]\s|,", titre)[0]  # garde le nom du produit, pas la fiche technique
    t = re.sub(r"^(processeur|casque|veste|maillot|jouet|baskets?|chaussures?|zapatillas( de)?|casco( de)?)\s+", "", t.strip(), flags=re.I)
    t = MOTS_VIDES.sub(" ", t)
    t = re.sub(r"[^\w\s\-+.]", " ", t)
    return " ".join(t.split()[:mots])


def chercher(tok, q, marche="EBAY_FR", neuf=None, limite=50):
    filtres = ["buyingOptions:{FIXED_PRICE}", "priceCurrency:EUR" if marche != "EBAY_GB" else "priceCurrency:GBP"]
    if neuf is True:
        filtres.append("conditionIds:{1000}")
    elif neuf is False:
        filtres.append("conditionIds:{1500|2000|2500|3000|4000|5000}")
    params = urllib.parse.urlencode({"q": q, "limit": limite, "filter": ",".join(filtres)})
    req = urllib.request.Request(f"{SEARCH_URL}?{params}", headers={
        "Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": marche,
        "Accept-Language": "fr-FR" if marche == "EBAY_FR" else "en-GB"})
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.loads(r.read()).get("itemSummaries", [])
    prix = []
    for it in items:
        try:
            prix.append(float(it["price"]["value"]))
        except (KeyError, TypeError, ValueError):
            continue
    return prix, [{"titre": it.get("title"), "prix": it.get("price", {}).get("value"), "url": it.get("itemWebUrl")}
                  for it in items[:3]]


def resume(prix, prix_achat):
    """Écarte les annonces sans rapport (accessoires à 3 €, lots) puis donne des repères prudents."""
    prix = sorted(p for p in prix if p >= prix_achat * 0.4)
    if len(prix) < 3:
        return None
    q = statistics.quantiles(prix, n=4)
    return {"nb": len(prix), "min": prix[0], "p25": round(q[0], 2), "mediane": round(q[1], 2), "max": prix[-1]}


def controler(candidats, maxi=15):
    bilan = {"faits": 0, "erreurs": []}
    try:
        tok = jeton()
    except Exception as e:
        bilan["erreurs"].append(f"jeton eBay : {type(e).__name__}: {str(e)[:150]}")
        return bilan
    for c in candidats[:maxi]:
        q = requete(c["titre"])
        try:
            neuf, ex_n = chercher(tok, q, neuf=True)
            occ, ex_o = chercher(tok, q, neuf=False)
        except urllib.error.HTTPError as e:
            bilan["erreurs"].append(f"HTTP {e.code} : {e.read()[:150].decode(errors='replace')}")
            if e.code in (401, 403):
                return bilan
            continue
        except Exception as e:
            bilan["erreurs"].append(f"{type(e).__name__}")
            continue
        c["ebay"] = {"requete": q, "neuf": resume(neuf, c["prix"]), "occasion": resume(occ, c["prix"]),
                     "exemples": (ex_o or ex_n)[:3]}
        bilan["faits"] += 1
    return bilan


def plafond(c):
    """Prix de revente maximum crédible d'après eBay : premier quart des annonces (occasion si revente
    d'occasion, sinon neuf). None si eBay n'a pas assez d'annonces comparables."""
    e = c.get("ebay") or {}
    for cle in ("occasion", "neuf"):
        r = e.get(cle)
        if r:
            return r["p25"]
    return None
