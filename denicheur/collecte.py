"""Collecte des bons plans depuis les flux RSS (réseau Pepper + autres)."""
import hashlib
import html
import re
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (compatible; Denicheur/1.0; usage personnel)"
NS_PEPPER = "{http://www.pepper.com/rss}merchant"
ATOM = "{http://www.w3.org/2005/Atom}"
TAUX_PLN_EUR = 0.235


def _prix(texte):
    """'1 302,40€' / '£12.99' / '12.99 €' -> 1302.4 (None si absent)."""
    if not texte:
        return None
    t = texte.replace(" ", "").replace("\xa0", "").replace(" ", "")
    m = re.search(r"\d[\d.,]*", t)
    if not m:
        return None
    n = m.group(0).rstrip(".,")
    dernier = max(n.rfind("."), n.rfind(","))
    if dernier != -1 and len(n) - dernier - 1 in (1, 2):  # séparateur décimal
        entier, dec = n[:dernier], n[dernier + 1:]
    else:
        entier, dec = n, "0"
    entier = re.sub(r"[.,]", "", entier) or "0"
    try:
        return float(f"{entier}.{dec}")
    except ValueError:
        return None


def _devise(texte, pays):
    if texte and "£" in texte:
        return "GBP"
    return "GBP" if pays == "UK" else "EUR"


def _nettoyer(texte, n=300):
    texte = html.unescape(re.sub(r"<[^>]+>", " ", texte or ""))
    return re.sub(r"\s+", " ", texte).strip()[:n]


def lire_flux(source, timeout=25):
    """Retourne (liste_d_annonces, erreur_ou_None)."""
    req = urllib.request.Request(source["url"], headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            brut = r.read()
    except Exception as e:  # réseau, 403 anti-robot, etc.
        return [], f"{type(e).__name__}: {e}"[:200]
    try:
        racine = ET.fromstring(brut)
    except ET.ParseError as e:
        return [], f"XML illisible: {e}"[:200]
    items = [a for a in (_item(i, source) for i in racine.iter("item")) if a]
    items += [a for a in (_entree_atom(e, source) for e in racine.iter(ATOM + "entry")) if a]
    return items, None


def _item(item, source):
    titre = (item.findtext("title") or "").strip()
    lien = (item.findtext("link") or "").strip()
    if not titre or not lien:
        return None
    temperature = None
    m = re.match(r"^\s*(-?\d+)\s*°\s*-\s*(.*)$", titre)
    if m:
        temperature, titre = int(m.group(1)), m.group(2)
    marchand, prix_txt = None, None
    pm = item.find(NS_PEPPER)
    if pm is not None:
        marchand, prix_txt = pm.get("name"), pm.get("price")
    description = _nettoyer(item.findtext("description"))
    if prix_txt is None:  # flux classique : chercher un prix dans le titre, sinon dans le texte
        motif = r"(\d[\d\s.,]*)\s?€|£\s?(\d+[.,]?\d*)"
        m2 = re.search(motif, titre) or re.search(motif, description)
        prix_txt = m2.group(0) if m2 else None
    prix = _prix(prix_txt)
    if source["pays"] == "PL" and prix:  # złoty -> euros (taux prudent)
        prix = round(prix * TAUX_PLN_EUR, 2)
    return {
        "id": hashlib.sha1(lien.encode()).hexdigest()[:10],
        "titre": titre[:180],
        "temperature": temperature,
        "categorie": (item.findtext("category") or "").strip(),
        "marchand": marchand,
        "prix": prix,
        "devise": _devise(prix_txt, source["pays"]),
        "lien": lien,
        "date": (item.findtext("pubDate") or "").strip(),
        "source": source["id"],
        "pays": source["pays"],
        "description": description,
    }


def _entree_atom(e, source):
    """Flux au format Atom (ex. Les Numériques) : <entry><title/><link href/><summary/></entry>."""
    titre = (e.findtext(ATOM + "title") or "").strip()
    lien_el = e.find(ATOM + "link")
    lien = (lien_el.get("href") if lien_el is not None else "") or ""
    if not titre or not lien:
        return None
    resume = _nettoyer(e.findtext(ATOM + "summary") or e.findtext(ATOM + "content"))
    m = re.search(r"(\d[\d\s.,]*)\s?€", titre) or re.search(r"(\d[\d\s.,]*)\s?€", resume)
    cat = e.find(ATOM + "category")
    return {
        "id": hashlib.sha1(lien.encode()).hexdigest()[:10],
        "titre": titre[:180], "temperature": None,
        "categorie": cat.get("term", "") if cat is not None else "",
        "marchand": None, "prix": _prix(m.group(0)) if m else None, "devise": "EUR",
        "lien": lien, "date": (e.findtext(ATOM + "updated") or "").strip(),
        "source": source["id"], "pays": source["pays"], "description": resume,
    }


def lire_source(source, timeout=25):
    """Lecteur par défaut : API GraphQL pour le réseau Pepper (plus riche, RSS en secours), flux RSS sinon."""
    if source.get("type") == "pepper" and source.get("graphql", True):
        from . import pepper
        return pepper.lire(source, timeout)
    return lire_flux(source, timeout)


def collecter(sources, lecteur=lire_source):
    annonces, etat = [], {}
    vus = set()
    for s in sources:
        if not s.get("actif", True):
            continue
        items, err = lecteur(s)
        etat[s["id"]] = {"ok": err is None, "nb": len(items), "erreur": err}
        for a in items:
            if a["id"] not in vus:
                vus.add(a["id"])
                annonces.append(a)
    return annonces, etat
