"""CONTRÔLE DU PRIX SUR LA PAGE DU PRODUIT, avant toute alerte (incident du 05/11 : Makita LS1019L annoncée 515,75 € chez
ManoMano, vraie page à 751,75 € — le prix avait été lu sur une carte voisine de la page).
On relit la fiche du produit et on prend le prix « officiel » que les sites donnent à Google (JSON-LD schema.org,
balises meta/itemprop) : pas de prix découpé « 64 » + « ,90 ». Amazon : prix actuel Keepa (déjà dans l'annonce).
Renvoie {"statut": "ok"|"different"|"inconnu", "prix_page": float|None}."""
import json
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}
TOLERANCE = 0.05   # 5 % d'écart toléré (arrondis, port)


def _num(v):
    try:
        return round(float(str(v).replace(" ", "").replace(" ", "").replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


def prix_officiel(h):
    """Prix du produit principal de la page, depuis les données structurées. None si introuvable."""
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        pile = d if isinstance(d, list) else [d]
        while pile:
            o = pile.pop(0)
            if isinstance(o, dict):
                if o.get("@type") in ("Product", "ProductGroup") or "offers" in o:
                    of = o.get("offers")
                    of = of[0] if isinstance(of, list) and of else of
                    if isinstance(of, dict):
                        p = _num(of.get("price") or of.get("lowPrice"))
                        if p:
                            return p
                pile += [v for v in o.values() if isinstance(v, (dict, list))]
            elif isinstance(o, list):
                pile += o
    for motif in (r'<meta[^>]+(?:property|itemprop|name)="(?:product:price:amount|og:price:amount|price)"[^>]+content="([\d.,]+)"',
                  r'itemprop="price"[^>]*content="([\d.,]+)"', r'"price"\s*:\s*"?([\d]+(?:[.,]\d{1,2})?)"?'):
        m = re.search(motif, h)
        if m and _num(m.group(1)):
            return _num(m.group(1))
    return None


def controler(x, timeout=25):
    lien = x.get("lien") or ""
    k = x.get("keepa") or {}
    if re.search(r"amazon\.", lien) and k.get("prix_neuf"):
        p = k.get("prix_amazon") or k.get("prix_neuf")
        ecart = abs(p - x["prix"]) / max(p, 1)
        return {"statut": "ok" if ecart <= TOLERANCE or x["prix"] >= p else "different", "prix_page": p}
    if not lien.startswith("http") or "t.me/" in lien:
        return {"statut": "inconnu", "prix_page": None}
    try:
        with urllib.request.urlopen(urllib.request.Request(lien, headers=UA), timeout=timeout) as r:
            h = r.read(3_000_000).decode("utf-8", "ignore")
    except Exception:
        return {"statut": "inconnu", "prix_page": None}
    p = prix_officiel(h)
    if p is None:
        return {"statut": "inconnu", "prix_page": None}
    ecart = abs(p - x["prix"]) / max(p, 1)
    return {"statut": "ok" if ecart <= TOLERANCE else "different", "prix_page": p}
