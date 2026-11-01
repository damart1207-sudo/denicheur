"""Prix plancher automatique : le prix neuf le plus bas en France, lu sur les comparateurs.

Testé depuis GitHub (01/11/2026) : achatmoinscher (recherche) lisible ; 123comparer et ledenicheur
lisibles sur les pages produit (données schema.org) mais leur recherche est bloquée ; idealo et
Leboncoin bloquent les programmes (vérifiés par Claude dans le navigateur, à rythme humain).
Rythme poli : 1 requête toutes les 3 secondes, uniquement pour les affaires candidates.
"""
import html as _html
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_ouvreur = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
_dernier = [0.0]


def _lire(url):
    attente = 3 - (time.time() - _dernier[0])
    if attente > 0:
        time.sleep(attente)
    _dernier[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml"})
    with _ouvreur.open(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def _prix(t):
    t = t.replace("\xa0", "").replace(" ", "").replace("€", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _norm(t):
    t = _html.unescape(t).lower()
    t = re.sub(r"(\d)\s*(go|gb)\b", r"\1 go", t)
    t = re.sub(r"(\d)\s*(to|tb)\b", r"\1 to", t)
    return t


def mots_cles(nom):
    return [m for m in re.findall(r"[\w+]+", _norm(nom)) if len(m) > 1 or m.isdigit()]


def correspond(titre, nom):
    """Tous les mots du nom doivent être présents EN MOTS ENTIERS (« 17 » ne correspond pas à « 17e »)."""
    t = _norm(titre)
    return all(re.search(r"(?<![\w+])" + re.escape(m) + r"(?![\w+])", t) for m in mots_cles(nom))


def achatmoinscher(nom, neuf=True):
    url = "https://www.achatmoinscher.com/recherche.php?" + urllib.parse.urlencode(
        {"q": nom, "pMin": 0, "pMax": 9999, "etat": 1 if neuf else 0, "date": 1, "typeRech": 1, "onlyTitle": 1})
    h = _lire(url)
    res = []
    for bloc in h.split('<div class="product-body">')[1:]:
        m_nom = re.search(r'class="product-name">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', bloc, re.S)
        m_prix = re.search(r'class="product-price">([^<]+)<', bloc)
        m_nb = re.search(r'(\d+)\s*e-boutiques?', bloc)
        if not (m_nom and m_prix):
            continue
        p = _prix(m_prix.group(1))
        if p:
            res.append({"titre": _html.unescape(re.sub(r"<[^>]+>", "", m_nom.group(2))).strip(), "prix": p,
                        "nb_boutiques": int(m_nb.group(1)) if m_nb else None,
                        "lien": urllib.parse.urljoin("https://www.achatmoinscher.com", m_nom.group(1))})
    return res


def schema_produit(url):
    """Lit les données schema.org d'une page produit (123comparer, ledenicheur...)."""
    h = _lire(url)
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if d.get("@type") in ("Product", "ProductGroup"):
            return d
    return None


def prix_plancher(nom):
    """Prix neuf le plus bas en France pour CE produit exact (mots entiers), avec la source."""
    rapport = {"nom": nom, "sources": {}}
    try:
        offres = [o for o in achatmoinscher(nom) if correspond(o["titre"], nom)]
        offres.sort(key=lambda o: o["prix"])
        rapport["sources"]["achatmoinscher"] = {"nb_produits": len(offres), "meilleur": offres[0] if offres else None,
                                               "autres": offres[1:4]}
    except Exception as e:
        rapport["sources"]["achatmoinscher"] = {"erreur": f"{type(e).__name__}: {str(e)[:100]}"}
    meilleurs = [s["meilleur"] for s in rapport["sources"].values() if s.get("meilleur")]
    if meilleurs:
        b = min(meilleurs, key=lambda o: o["prix"])
        rapport["prix_min"], rapport["ou"], rapport["lien"] = b["prix"], "achatmoinscher", b["lien"]
    return rapport
