"""Prix de l'offre principale, en EUR et en stock. Donnée absente = inconnue."""
import json
import math
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import urllib.request
from .validation import meme_prix, recent, url_produit

UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "fr-FR,fr;q=0.9"}
INTERMEDIAIRES = ("dealabs.com", "chollometro.com", "mydealz.de", "pepper.com", "pepper.pl", "pepper.nl", "hotukdeals.com", "lesnumeriques.com", "clubic.com")


def _num(v):
    try:
        if isinstance(v, bool):
            return None
        n = float(str(v).replace("\u00a0", "").replace(" ", "").replace(",", "."))
        return round(n, 2) if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError):
        return None


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts, self.canonicals = [], []
        self.buffer = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self.buffer = []
        if tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonicals.append(a.get("href", ""))

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.buffer is not None:
            self.scripts.append("".join(self.buffer))
            self.buffer = None


def _types(o):
    t = o.get("@type", [])
    return set(t if isinstance(t, list) else [t])


def offre_officielle(h, lien=None, identifiants=None):
    """Sélection par URL/GTIN/SKU ou produit unique sur canonique concordante.

    Pas de recherche récursive dans recommandations, listes ou variantes.
    Sans URL cible, seul un produit unique est accepté (diagnostic uniquement).
    """
    page = _Page()
    page.feed(h)
    produits = []
    for s in page.scripts:
        try:
            d = json.loads(s)
        except (ValueError, TypeError):
            continue
        racines = d if isinstance(d, list) else [d]
        for o in racines:
            if isinstance(o, dict):
                graph = o.get("@graph", [])
                if isinstance(graph, list):
                    produits.extend(n for n in graph if isinstance(n, dict) and "Product" in _types(n))
                if "Product" in _types(o):
                    produits.append(o)
    selection = []
    ids = {str(i) for i in (identifiants or []) if i}
    for p in produits:
        urls = [p.get("url"), p.get("@id")]
        vals = {str(p[k]) for k in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14", "sku") if p.get(k)}
        if ids and vals and not (ids & vals):
            continue  # Une URL commune ne permet pas d'ignorer une variante explicitement différente.
        explicites = [u for u in urls if isinstance(u, str) and not u.startswith("#")]
        correspond = lien and any(url_produit(urljoin(lien, u)) == url_produit(lien) for u in explicites)
        canonique = lien and not explicites and len(produits) == 1 and any(
            url_produit(urljoin(lien, u)) == url_produit(lien) for u in page.canonicals)
        if (not lien and len(produits) == 1) or correspond or (ids & vals) or canonique:
            selection.append(p)
    if len(selection) != 1:
        return None
    offres = selection[0].get("offers", [])
    offres = offres if isinstance(offres, list) else [offres]
    prix = []
    for o in offres:
        if not isinstance(o, dict) or "AggregateOffer" in _types(o):
            continue
        if str(o.get("priceCurrency", "")).upper() != "EUR":
            continue
        if str(o.get("availability", "")).rstrip("/").split("/")[-1] != "InStock":
            continue
        if lien and o.get("url") and url_produit(urljoin(lien, o["url"])) != url_produit(lien):
            continue
        n = _num(o.get("price"))
        if n is not None:
            prix.append({'prix': n, 'offre': o, 'produit': selection[0]})
    return prix[0] if len(prix) == 1 else None


def prix_officiel(h, lien=None, identifiants=None):
    detail = offre_officielle(h, lien, identifiants)
    return detail['prix'] if detail else None


def controler(x, timeout=25):
    lien = x.get("lien_marchand") or (x.get("page_offre") or {}).get("lien_marchand") or x.get("lien") or ""
    inconnu = {"statut": "inconnu", "prix_page": None, "lien": lien}
    if x.get("devise", "EUR") != "EUR":
        return inconnu
    preuve = None
    if not url_produit(lien):
        return inconnu
    host = urlsplit(lien).hostname or ""
    if any(host == d or host.endswith("." + d) for d in INTERMEDIAIRES):
        return inconnu
    # L'ancien booléen prix_verifie ne suffit pas : reçu PC explicite et daté.
    recu = x.get("preuve_prix") or {}
    if (recent(recu.get("verifie_le")) and url_produit(recu.get("lien")) == url_produit(lien)
            and recu.get("devise") == "EUR" and recu.get("disponibilite") == "InStock"
            and recu.get("identite_confirmee") is True and _num(recu.get("prix_page")) is not None):
        p, date = _num(recu["prix_page"]), recu["verifie_le"]
        preuve = recu.get("preuve_livraison")
    else:
        try:
            with urllib.request.urlopen(urllib.request.Request(lien, headers=UA), timeout=timeout) as r:
                if url_produit(r.geturl()) != url_produit(lien):
                    return inconnu
                h = r.read(3_000_000).decode("utf-8", "replace")
            detail = offre_officielle(h, lien, [x.get("ean"), x.get("sku")])
            p = detail['prix'] if detail else None
            date = datetime.now(timezone.utc).isoformat(timespec="seconds")
            from .logistique import depuis_offre
            preuve = depuis_offre(detail, lien, date)
        except Exception:
            return inconnu
    if p is None:
        return inconnu
    return {"statut": "ok" if meme_prix(p, x.get("prix")) else "different",
            "prix_page": p, "verifie_le": date, "lien": lien, "preuve_livraison": preuve}
