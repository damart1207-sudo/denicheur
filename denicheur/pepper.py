"""Lecture des sites du réseau Pepper (Dealabs, mydealz, hotukdeals, Chollometro, Pepper PL/NL, Preisjäger)
par leur API interne GraphQL (celle de l'application mobile), à la place du flux RSS.

Pourquoi : le RSS ne donne que 30 titres. GraphQL donne plus de deals et surtout des champs en plus :
le prix de référence ailleurs (nextBestPrice), le code promo, le marchand propre, le statut expiré,
le type (deal / bon de réduction / gratuit) et les groupes (catégories).
Technique reprise des projets ouverts chollo-alerts (ES) et ha-pepper (DE), 11/2026.

Rythme poli : une page d'accueil (cookies) puis 1 requête par liste, 1,5 s de pause ; en cas d'échec
(HTTP 418 du pare-feu, changement d'API), on retombe sur le flux RSS : rien n'est perdu.
"""
import hashlib
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request

from . import collecte

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PAUSE = 1.5

CHAMPS = """threadId title url price nextBestPrice temperature publishedAt createdAt pickedAt description
voucherCode type status isExpired expirable commentCount shareCount
mainImage { path name } merchant { merchantId name pageUrl urlName } user { userId username } groups { groupsPath }"""

REQUETES = {
    "hot": ("HottestWidget", "query HottestWidget($filter: ThreadFilter!) { hottestWidget(filter: $filter) { threads { %s } } }" % CHAMPS),
    "new": ("getThreads", "query getThreads($filter: ThreadFilter!) { threads(filter: $filter) { %s } }" % CHAMPS),
}

_sessions = {}  # domaine -> (ouvreur, xsrf)


def _session(domaine):
    if domaine in _sessions:
        return _sessions[domaine]
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(f"https://{domaine}/", headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                                                                  "Accept": "text/html,application/xhtml+xml"})
    with op.open(req, timeout=25) as r:
        r.read()
    xsrf = next((c.value for c in cj if c.name == "xsrf_t"), "")
    _sessions[domaine] = (op, urllib.parse.unquote(xsrf))
    time.sleep(PAUSE)
    return _sessions[domaine]


def requete(domaine, liste="new", filtre=None):
    """Renvoie la liste brute des threads (dict GraphQL) d'une liste 'hot' ou 'new'."""
    op, xsrf = _session(domaine)
    nom, q = REQUETES[liste]
    corps = json.dumps({"operationName": nom, "variables": {"filter": filtre or {}}, "query": q}).encode()
    req = urllib.request.Request(f"https://{domaine}/graphql", data=corps, headers={
        "User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest", "X-Xsrf-Token": xsrf, "Referer": f"https://{domaine}/",
        "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"})
    with op.open(req, timeout=30) as r:
        d = json.loads(r.read())
    time.sleep(PAUSE)
    if d.get("errors"):
        raise RuntimeError("GraphQL: " + json.dumps(d["errors"])[:300])
    data = d.get("data") or {}
    if liste == "hot":
        return ((data.get("hottestWidget") or {}).get("threads")) or []
    return data.get("threads") or []


def _lien(domaine, t):
    u = t.get("url") or ""
    if u and not u.startswith("http"):
        u = f"https://{domaine}{u if u.startswith('/') else '/' + u}"
    return u


def annonce(t, source, domaine):
    """Convertit un thread GraphQL au format des annonces du Dénicheur (même id que le RSS : sha1 du lien)."""
    lien = _lien(domaine, t)
    titre = (t.get("title") or "").strip()
    if not titre or not lien:
        return None
    prix = t.get("price")
    try:
        prix = float(prix) if prix not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        prix = None
    ref = t.get("nextBestPrice")
    try:
        ref = float(ref) if ref not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        ref = None
    if source["pays"] == "PL":
        prix = round(prix * collecte.TAUX_PLN_EUR, 2) if prix else None
        ref = round(ref * collecte.TAUX_PLN_EUR, 2) if ref else None
    m = t.get("merchant") or {}
    groupes = [g.get("groupsPath") for g in (t.get("groups") or []) if isinstance(g, dict) and g.get("groupsPath")]
    typ = str(t.get("type") or "").lower()
    return {
        "id": hashlib.sha1(lien.encode()).hexdigest()[:10],
        "titre": titre[:180],
        "temperature": int(t["temperature"]) if isinstance(t.get("temperature"), (int, float)) else None,
        "categorie": (groupes[0] if groupes else ""),
        "marchand": m.get("name"),
        "prix": prix,
        "prix_reference": ref,              # prix ailleurs (annoncé par la communauté) : à contrôler, jamais une preuve
        "economie_annoncee_pct": round((1 - prix / ref) * 100) if prix and ref and ref > prix else None,
        "devise": "GBP" if source["pays"] == "UK" else "EUR",
        "lien": lien,
        "date": str(t.get("publishedAt") or t.get("createdAt") or ""),
        "source": source["id"],
        "pays": source["pays"],
        "description": collecte._nettoyer(t.get("description") or ""),
        "code_promo": t.get("voucherCode") or None,
        "type_deal": typ or None,            # deal / voucher / freebie / discussion
        "expire": bool(t.get("isExpired")),
        "nb_commentaires": t.get("commentCount"),
        "lecture": "graphql",
    }


def lire(source, timeout=25):
    """Lecteur d'une source 'pepper' : GraphQL d'abord, flux RSS en secours. Renvoie (annonces, erreur)."""
    domaine = urllib.parse.urlparse(source["url"]).netloc
    liste = "hot" if re.search(r"/rss/(hot|tendance)", source["url"]) else "new"
    try:
        threads = requete(domaine, liste)
        items = [a for a in (annonce(t, source, domaine) for t in threads if isinstance(t, dict)) if a]
        items = [a for a in items if not a["expire"] and a["type_deal"] in (None, "deal")]
        if items:
            return items, None
        erreur = "GraphQL : aucun deal"
    except Exception as e:
        erreur = f"GraphQL {type(e).__name__}: {str(e)[:120]}"
    items, err_rss = collecte.lire_flux(source, timeout)
    for a in items:
        a["lecture"] = "rss"
    return items, (None if err_rss is None else f"{erreur} | RSS {err_rss}")
