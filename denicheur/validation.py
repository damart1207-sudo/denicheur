"""Contrôles communs aux fiches, aux rapports et à la publication publique."""
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

MAX_AGE_SECONDES = 900


def url_produit(url):
    """Conserve les paramètres de variante ; retire seulement le suivi reconnu."""
    if not isinstance(url, str):
        return ""
    try:
        p = urlsplit(url)
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in ("gclid", "fbclid")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(sorted(q)), ""))


def recent(iso, maintenant=None):
    try:
        d = datetime.fromisoformat(iso)
        if d.tzinfo is None:
            return False
        age = ((maintenant or datetime.now(timezone.utc)) - d).total_seconds()
        return 0 <= age <= MAX_AGE_SECONDES
    except (ValueError, TypeError):
        return False


def meme_prix(a, b):
    return (isinstance(a, (int, float)) and not isinstance(a, bool)
            and isinstance(b, (int, float)) and not isinstance(b, bool)
            and math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0
            and abs(a - b) <= 0.011)


def blocages(x):
    """Absence de preuve = piste interne, jamais confirmation commerciale."""
    erreurs = []
    v = x.get("controle_prix") or {}
    lien = x.get("lien_marchand") or (x.get("page_offre") or {}).get("lien_marchand") or x.get("lien")
    if (v.get("statut") != "ok" or not recent(v.get("verifie_le"))
            or not meme_prix(v.get("prix_page"), x.get("prix"))
            or not url_produit(lien) or url_produit(v.get("lien")) != url_produit(lien)):
        erreurs.append("prix marchand non confirmé récemment pour cette offre")
    if (x.get("meme_produit") or {}).get("meme") is not True:
        erreurs.append("même produit exact non confirmé")
    if x.get("livraison_fr_confirmee") is not True:
        erreurs.append("livraison en France non confirmée")
    if x.get("cout_total_confirme") is not True:
        erreurs.append("coût total livré non confirmé")
    return erreurs
