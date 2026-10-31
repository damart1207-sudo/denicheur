"""Vérificateur de prix : Gemini cherche sur Google (comme l'« Aperçu IA ») le prix neuf le plus bas
en France et la fourchette d'occasion, avec ses sources. Le prix de revente retenu devient le plus
prudent des trois : estimation de l'équipe, haut de la fourchette d'occasion, 85 % du neuf le moins cher.

Gratuit : quota mensuel de recherches Google inclus dans l'offre gratuite de Gemini.
Aucun moyen de paiement n'est enregistré : au-delà du quota, l'appel échoue simplement.
"""
import json
import os
import urllib.error
import urllib.request

from .ia import extraire_json

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"

CONSIGNE = """Cherche sur Google les prix actuels en France de ce produit : « {titre} ».
Je l'achète {prix} chez {marchand}. Donne :
- le prix NEUF le plus bas trouvé aujourd'hui chez un vrai marchand français ou européen livrant en France (hors ce bon plan) ;
- la fourchette de prix d'OCCASION constatée (Leboncoin, Vinted, eBay, Back Market) ;
- si le produit se revend facilement.
Réponds uniquement avec ce JSON :
{{"produit_identifie": "...", "prix_neuf_min": <nombre ou null>, "marchand_neuf_min": "...",
"occasion_bas": <nombre ou null>, "occasion_haut": <nombre ou null>, "revente_facile": true|false,
"remarque": "<une phrase en français>"}}"""


def verifier_prix(candidats, cle=None, modeles=("gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"), maxi=15):
    cle = cle or os.environ.get("GEMINI_API_KEY", "").strip()
    bilan = {"faits": 0, "erreurs": []}
    if not cle:
        bilan["erreurs"].append("clé Gemini absente")
        return bilan
    for c in candidats[:maxi]:
        devise = "£" if c.get("devise") == "GBP" else "€"
        texte = CONSIGNE.format(titre=c["titre"], prix=f"{c['prix']:.2f} {devise}", marchand=c.get("marchand") or "?")
        corps = {"contents": [{"role": "user", "parts": [{"text": texte}]}], "tools": [{"google_search": {}}]}
        rep = None
        for modele in modeles:
            req = urllib.request.Request(URL.format(modele=modele) + f"?key={cle}", data=json.dumps(corps).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": "denicheur/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    rep = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 402 or e.code == 403:
                    bilan["erreurs"].append(f"HTTP {e.code} : vérification arrêtée")
                    return bilan
                bilan["erreurs"].append(f"HTTP {e.code} ({modele})")
                if e.code == 429 and modele == modeles[-1] and bilan["faits"] == 0:
                    bilan["erreurs"].append("quota Google épuisé : vérification reportée")
                    return bilan
                continue
            except Exception as e:
                bilan["erreurs"].append(f"{type(e).__name__} ({modele})")
                continue
        if not rep:
            continue
        try:
            cand = rep["candidates"][0]
            texte_rep = "".join(p.get("text", "") for p in cand["content"]["parts"])
        except (KeyError, IndexError):
            continue
        data = extraire_json(texte_rep) or {}
        sources = [{"titre": ch.get("web", {}).get("title"), "url": ch.get("web", {}).get("uri")}
                   for ch in cand.get("groundingMetadata", {}).get("groundingChunks", [])][:5]
        appliquer(c, data, sources)
        bilan["faits"] += 1
    return bilan


def _nombre(v):
    try:
        v = float(v)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def appliquer(c, data, sources):
    neuf = _nombre(data.get("prix_neuf_min"))
    occ_haut = _nombre(data.get("occasion_haut"))
    plafonds = [c["prix_revente_estime"]]
    if occ_haut:
        plafonds.append(occ_haut)
    if neuf:
        plafonds.append(round(neuf * 0.85, 2))
    revente = min(plafonds)
    c["verification"] = {
        "produit": data.get("produit_identifie"),
        "prix_neuf_min": neuf, "marchand_neuf_min": data.get("marchand_neuf_min"),
        "occasion_bas": _nombre(data.get("occasion_bas")), "occasion_haut": occ_haut,
        "revente_facile": data.get("revente_facile"), "remarque": data.get("remarque"),
        "prix_revente_prudent": revente, "sources": sources,
        "deja_moins_cher_ailleurs": bool(neuf and neuf <= c["prix"]),
    }
