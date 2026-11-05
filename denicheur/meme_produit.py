"""MÊME PRODUIT ? (piège du 05/11 : lot de 2 roues gonflables ManoMano 13,79 € comparé à un lot de 8 roues pleines
Leroy Merlin 94,95 €). Avant de déclarer un bingo, on vérifie que les deux offres portent sur le MÊME produit :
 1. quantité (lot de N, x N, N pièces, pack de N…) -> prix à l'unité ;
 2. caractéristiques opposées (gonflable / plein, filaire / sans fil, dimensions, capacités, puissances) ;
 3. verdict final par Gemini (même modèle, même variante, même quantité ?), en cache.
Renvoie {"meme": True/False/None, "raison": "...", "qte_a", "qte_b"}."""
import json
import os
import re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_CACHE = os.path.join(RACINE, "data/base/meme_produit.json")

QTE = re.compile(r"(?:lot|pack|set|boite|boîte|coffret|carton)\s*(?:de|of)?\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:x|×)\s*(?!\d)|\b(\d{1,3})\s*(?:pcs?|pi[èe]ces?|unit[ée]s?|pack|rouleaux|sachets?|capsules|dosettes|ampoules|piles|paires?)\b|\bx\s?(\d{1,3})\b", re.I)
OPPOSES = [("gonflable", r"plein|increvable|pu\b|mousse"), ("sans fil|wifi|bluetooth|batterie", r"filaire"),
           ("neuf", r"occasion|reconditionn"), ("digital|num[ée]rique", r"disque|lecteur"), ("pro\b", r"\blite\b|\bmini\b")]
MESURES = re.compile(r"(\d{2,4})\s?[x×]\s?(\d{2,4})|\b(\d{1,4})\s?(go|gb|to|tb|w|kw|mah|ah|l|ml|cl|kg|g|cm|mm|m|pouces?|\")\b", re.I)


def _n(t):
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def quantite(titre):
    t = _n(titre)
    for m in QTE.finditer(t):
        v = next((g for g in m.groups() if g), None)
        if v and 1 < int(v) <= 500:
            return int(v)
    return 1


def mesures(titre):
    out = set()
    for m in MESURES.finditer(_n(titre)):
        if m.group(1):
            out.add(f"{m.group(1)}x{m.group(2)}")
        else:
            out.add(f"{m.group(3)}{m.group(4).lower().rstrip('s')}")
    return out


def mecanique(titre_a, titre_b):
    """Tests sans IA. Renvoie (verdict, raison) ; verdict None = pas de contradiction trouvée, à confirmer par l'IA."""
    a, b = _n(titre_a), _n(titre_b)
    qa, qb = quantite(a), quantite(b)
    if qa != qb:
        return False, f"quantités différentes ({qa} contre {qb})"
    for x, y in OPPOSES:
        if (re.search(x, a) and re.search(y, b) and not re.search(x, b)) or (re.search(x, b) and re.search(y, a) and not re.search(x, a)):
            return False, f"caractéristiques opposées ({x.split('|')[0]} / {y.split('|')[0]})"
    ma, mb = mesures(a), mesures(b)
    if ma and mb and not (ma & mb):
        return False, f"dimensions/capacités différentes ({', '.join(sorted(ma)[:3])} contre {', '.join(sorted(mb)[:3])})"
    return None, ""


def _cache():
    try:
        return json.load(open(F_CACHE, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def ia(titre_a, titre_b, prix_a=None, prix_b=None):
    """Gemini : même produit exact ? Cache par paire. None si l'IA est indisponible."""
    cle = (_n(titre_a)[:120] + " || " + _n(titre_b)[:120])
    c = _cache()
    if cle in c:
        return c[cle].get("meme"), c[cle].get("raison", "")
    try:
        from .ia import Agent, extraire_json
        conf = json.load(open(os.path.join(RACINE, "config/equipe.json"), encoding="utf-8")).get("agents", {}).get("gemini")
        if not conf:
            return None, ""
        rep = Agent("gemini", {**conf, "max_appels": 1, "timeout": 60}).demander(
            "Tu compares deux offres de vente en ligne. JSON uniquement.",
            "Ces deux offres portent-elles EXACTEMENT sur le même produit (même marque, même modèle, même variante : taille, capacité, "
            "couleur si elle change le prix, même quantité dans le lot, même état neuf) ? Réponds strictement en JSON : "
            '{"meme": true|false, "raison": "une phrase courte"}.\n'
            f"Offre A : {titre_a[:200]}" + (f" — {prix_a} €" if prix_a else "") + "\n"
            f"Offre B : {titre_b[:200]}" + (f" — {prix_b} €" if prix_b else ""))
        d = extraire_json(rep) if rep else None
        if not isinstance(d, dict) or not isinstance(d.get("meme"), bool):
            return None, ""
        c[cle] = {"meme": d["meme"], "raison": str(d.get("raison", ""))[:160]}
        os.makedirs(os.path.dirname(F_CACHE), exist_ok=True)
        json.dump(dict(list(c.items())[-5000:]), open(F_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        return d["meme"], c[cle]["raison"]
    except Exception:
        return None, ""


def verifier(titre_a, titre_b, prix_a=None, prix_b=None, avec_ia=True):
    v, raison = mecanique(titre_a, titre_b)
    if v is False:
        return {"meme": False, "raison": raison, "qte_a": quantite(titre_a), "qte_b": quantite(titre_b)}
    if avec_ia:
        v2, r2 = ia(titre_a, titre_b, prix_a, prix_b)
        if v2 is not None:
            return {"meme": v2, "raison": r2, "qte_a": quantite(titre_a), "qte_b": quantite(titre_b)}
    return {"meme": None, "raison": "non confirmé", "qte_a": quantite(titre_a), "qte_b": quantite(titre_b)}
