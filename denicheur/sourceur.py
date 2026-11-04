"""SOURCEUR (dénicheur E, spécialiste des BINGOS, demandé par David le 04/11) : pour chaque bingo, cherche comment se
fournir au plus bas : fabricant et pays de fabrication, distributeurs officiels France/Europe, grossistes (BigBuy, Merkandi,
Ingram, Tech Data…), usines/fournisseurs Alibaba-1688 avec quantité minimum et prix d'usine, qui contacter et comment,
et un message de négociation prêt à envoyer. Distingue les MARQUES FERMÉES (ghd, Beats, Apple… : pas de prix d'usine,
seulement distributeurs agréés, déstockages et achats en gros) des PRODUITS D'USINE (chaise Sihoo, accessoires, cosmétiques
coréens… : usine ou fournisseur direct possible).

Outil : Gemini avec recherche Google (déjà utilisé pour la vérification des prix), sources citées. Quelques centimes par fiche.
RIEN n'est envoyé automatiquement : David contacte lui-même. -> data/sourcing.json (onglet « Sourceur » du rapport)
python -m denicheur.sourceur   (fiches manquantes des bingos du jour, ≤ 10)"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .ia import extraire_json

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(RACINE, "data/sourcing.json")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"
MODELES = ("gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash")

CONSIGNE = """Tu es acheteur professionnel pour un petit revendeur français (micro-entreprise). Produit très recherché et peu vendu
en France (« bingo ») : « {produit} » (marque {marque}). Prix neuf le moins cher en France : {prix_fr} €. Ventes Amazon.fr estimées : {ventes} / mois.
Cherche sur Google (en français et en anglais) comment s'en fournir AU PLUS BAS PRIX pour le revendre en France, et réponds UNIQUEMENT en JSON :
{{"type": "marque_fermee|produit_usine|mixte",
  "fabricant": "...", "pays_fabrication": "...",
  "distributeurs_officiels": [{{"nom": "...", "pays": "...", "site": "...", "comment_contacter": "...", "conditions": "compte pro / minimum"}}],
  "grossistes": [{{"nom": "...", "site": "...", "prix_ou_remise": "...", "minimum": "...", "note": "..."}}],
  "usines_ou_fournisseurs": [{{"nom": "...", "plateforme": "Alibaba|1688|Made-in-China|direct", "lien": "...", "prix_unitaire_estime_eur": 0, "quantite_minimum": 0, "delai_jours": 0, "note": "..."}}],
  "meilleure_piste": "<la voie la plus réaliste pour un petit revendeur, en une phrase>",
  "prix_achat_cible_eur": 0, "marge_possible_pct": 0,
  "risques": ["contrefaçon", "garantie", "normes CE", "droits de douane", "..."],
  "message_negociation": "<message en français (ou anglais si fournisseur étranger) prêt à envoyer, 5 lignes, sans inventer de prix>",
  "sources": ["url", "..."]}}
Règles : n'invente aucun contact ni prix ; si tu ne trouves pas, mets des listes vides et explique dans meilleure_piste. Pour une marque fermée
(distribution contrôlée), dis-le et oriente vers distributeurs agréés, déstockeurs, achats en gros sur Amazon Business ou ventes privées."""


def _lire():
    try:
        return json.load(open(F, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"fiches": {}}


def fiche(b, cle):
    """Une fiche sourcing pour un bingo (dict de data/bingo.json). Renvoie la fiche ou None."""
    texte = CONSIGNE.format(produit=b.get("titre") or b.get("mot_cle"), marque=b.get("marque") or "?",
                            prix_fr=b.get("prix_neuf_france") or b.get("prix") or "?", ventes=b.get("ventes_30j") or "?")
    corps = {"contents": [{"role": "user", "parts": [{"text": texte}]}], "tools": [{"google_search": {}}]}
    for modele in MODELES:
        req = urllib.request.Request(URL.format(modele=modele) + f"?key={cle}", data=json.dumps(corps).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "denicheur/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                rep = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (402, 403):
                return None
            continue
        except Exception:
            continue
    else:
        return None
    try:
        cand = rep["candidates"][0]
        texte_rep = "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError):
        return None
    d = extraire_json(texte_rep) or {}
    if not d:
        return None
    d["sources_google"] = [ch.get("web", {}).get("uri") for ch in cand.get("groundingMetadata", {}).get("groundingChunks", [])][:8]
    d["mot_cle"], d["titre"], d["asin"] = b.get("mot_cle"), b.get("titre"), b.get("asin")
    d["prix_fr"], d["recherches_mois"], d["vendeurs"] = b.get("prix_neuf_france") or b.get("prix"), b.get("recherches_mois"), b.get("vendeurs")
    d["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return d


def jour(maxi=10):
    cle = os.environ.get("GEMINI_API_KEY", "").strip()
    if not cle:
        print("sourceur : clé Gemini absente")
        return 0
    try:
        bingos = json.load(open(os.path.join(RACINE, "data/bingo.json"), encoding="utf-8")).get("bingos", [])
    except (OSError, json.JSONDecodeError):
        bingos = []
    d = _lire()
    faits = 0
    for b in bingos:
        k = b.get("asin") or b.get("mot_cle")
        if not k or k in d["fiches"] or faits >= maxi:
            continue
        f = fiche(b, cle)
        if f:
            d["fiches"][k] = f
            faits += 1
            print(f"  sourceur : {b.get('mot_cle')} -> {f.get('type')} ; {f.get('meilleure_piste', '')[:90]}")
    d["maj"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(F), exist_ok=True)
    json.dump(d, open(F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"sourceur : {faits} fiche(s) écrite(s), {len(d['fiches'])} au total")
    return faits


if __name__ == "__main__":
    jour()
