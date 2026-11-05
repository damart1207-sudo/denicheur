"""PROSPECTUS DES MAGASINS (promos en magasin, souvent absentes des sites web), lus par Gemini (vision).
Source : Bonial (regroupe les prospectus de presque toutes les enseignes de France) — page publique de chaque enseigne,
qui contient l'identifiant des prospectus en cours et leurs pages (images). Gemini lit chaque page et sort les produits
NON alimentaires avec prix, prix barré, dates de validité. -> data/prospectus.json + annonces pour la veille.
Coût : Gemini Flash, environ 1 000 à 2 000 jetons par page ; plafond PAGES_MAX par prospectus et PAGES_JOUR par jour.
Un prospectus n'est lu qu'une fois (cache par identifiant)."""
import base64
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_SORTIE = os.path.join(RACINE, "data/prospectus.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}
# non alimentaire d'abord (c'est ce qu'on revend) ; les hypermarchés ensuite
ENSEIGNES = ["Boulanger", "Darty", "Action", "Gifi", "Noz", "But", "Conforama", "Brico-Depot", "Leroy-Merlin", "Castorama",
             "Decathlon", "Intersport", "King-Jouet", "Cultura", "Lidl", "Aldi", "E-Leclerc", "Carrefour", "Auchan", "Intermarche"]
ALIMENTAIRE = re.compile(r"saumon|poulet|viande|fromage|jambon|lait|café|dosette|vin |champagne|bière|eau |jus |chocolat|biscuit|"
                         r"yaourt|beurre|pain|pâtes|riz|huile|lessive|papier hygi|essuie|couche|croquette|pâtée|surgel|légume|fruit|poisson|"
                         r"crevette|foie gras|whisky|rhum|vodka|apéritif|granul|bois de chauffage|fioul|pétrole", re.I)
PAGES_MAX = 2       # pages lues par Gemini par prospectus (les 2 premières, accessibles publiquement)
PAGES_JOUR = 40     # plafond quotidien de pages envoyées à Gemini (≈ quelques centimes)


def _get(url, binaire=False, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        b = r.read()
    return b if binaire else b.decode("utf-8", "ignore")


def _lire(f, d):
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return d


def page_enseigne(enseigne):
    return _get(f"https://www.bonial.fr/Enseignes/{enseigne}")


def prospectus_enseigne(enseigne, h=None):
    """[(id, nb_pages, [urls des pages accessibles])] des prospectus en cours (la page publique expose les 1res pages)."""
    h = h or page_enseigne(enseigne)
    out = []
    for m in re.finditer(r'"contentId":"([0-9a-f-]{36})"', h):
        cid = m.group(1)
        bloc = h[m.start():m.start() + 8000]
        n = re.search(r'"pageCount":(\d+)', bloc)
        urls = list(dict.fromkeys(re.findall(r'"normal":"(https://content-media\.bonial\.biz/[^"]+)"', bloc)))[:4]
        if cid not in [o[0] for o in out] and urls:
            out.append((cid, int(n.group(1)) if n else len(urls), urls))
    return out


def offres_enseigne(enseigne, h=None):
    """Grille « Promos disponibles dans les catalogues » : marque, produit, prix — déjà structurés (pas besoin d'IA)."""
    h = h or page_enseigne(enseigne)
    out = []
    for m in re.finditer(r'<img alt="Promo ([^"]+?) à ([\d\s ,.]+)\s?€[^"]*"[^>]*src="([^"]+)".*?<p class="text-dark1 truncate text-sm">([^<]*)</p>'
                         r'<p class="truncate font-semibold">([^<]*)</p>.*?<p class="mr-sm text-primary[^"]*">\s*([\d\s ,.]+)\s?€', h, re.S):
        marque, produit = m.group(4).strip(), m.group(5).strip()
        try:
            prix = float(m.group(6).replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        out.append({"nom": produit, "marque": marque, "prix": prix, "image": m.group(3)})
    return out


def lire_page(image, enseigne):
    """Gemini (vision) : produits non alimentaires de la page, en JSON."""
    cle = os.environ.get("GEMINI_API_KEY", "").strip()
    if not cle:
        return []
    conf = _lire(os.path.join(RACINE, "config/equipe.json"), {}).get("agents", {}).get("gemini", {})
    modeles = [conf.get("modele", "gemini-2.5-flash")] + conf.get("modeles_secours", [])
    consigne = ("Page d'un prospectus de l'enseigne " + enseigne + ". Liste UNIQUEMENT les produits NON alimentaires "
                "(high-tech, électroménager, maison, bricolage, jardin, jouets, sport, beauté, mode) de 15 € ou plus. "
                "Pour chacun : marque et modèle exacts si visibles, prix promo, prix barré/avant si affiché, % de remise, "
                "dates de validité de l'offre, conditions (carte fidélité, remise en bon d'achat, ODR…). "
                'JSON uniquement : {"produits":[{"nom":"","marque":"","prix":0,"prix_avant":null,"remise_pct":null,'
                '"valable_du":"","valable_au":"","conditions":""}]}. Si aucun, {"produits":[]}.')
    corps = {"contents": [{"parts": [{"text": consigne}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}}]}],
             "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}}
    for modele in modeles:
        try:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent?key={cle}",
                                         data=json.dumps(corps).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            texte = d["candidates"][0]["content"]["parts"][0]["text"]
            return (json.loads(texte) or {}).get("produits", [])
        except Exception:
            continue
    return []


def tour(enseignes=None, pages_jour=PAGES_JOUR):
    base = _lire(F_SORTIE, {"lus": {}, "produits": []})
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    budget = pages_jour  # une exécution par jour (passage de nuit)
    bilan = {"enseignes": 0, "prospectus": 0, "pages": 0, "produits": 0, "erreurs": []}
    nouveaux = []
    for ens in (enseignes or ENSEIGNES):
        if budget <= 0:
            break
        try:
            h = page_enseigne(ens)
            liste = prospectus_enseigne(ens, h)
            offres = offres_enseigne(ens, h)
        except Exception as e:
            bilan["erreurs"].append(f"{ens}: {type(e).__name__}")
            continue
        bilan["enseignes"] += 1
        validite = re.search(r"(\d{2}/\d{2}/\d{4}) - (\d{2}/\d{2}/\d{4})", h)
        du, au = ((lambda d: f"{d[6:]}-{d[3:5]}-{d[:2]}")(validite.group(1)), (lambda d: f"{d[6:]}-{d[3:5]}-{d[:2]}")(validite.group(2))) if validite else (None, None)
        for o in offres:
            if o["prix"] < 15 or ALIMENTAIRE.search(o["nom"] + " " + o["marque"]):
                continue
            nom = " ".join(x for x in (o["marque"], o["nom"]) if x).strip()
            nouveaux.append({"id": hashlib.sha1(f"{ens}{nom}{o['prix']}".encode()).hexdigest()[:10], "titre": nom[:160], "prix": o["prix"],
                             "prix_avant": None, "remise_pct": None, "valable_du": du, "valable_au": au, "conditions": "",
                             "marchand": ens.replace("-", " "), "prospectus": "offres", "page": 0,
                             "lien": f"https://www.bonial.fr/Enseignes/{ens}", "vu": jour, "image": o["image"]})
        bilan["offres_structurees"] = bilan.get("offres_structurees", 0) + len(offres)
        for cid, nb, urls in liste[:2]:
            if cid in base["lus"] or budget <= 0:
                continue
            bilan["prospectus"] += 1
            for i, u in enumerate(urls[:PAGES_MAX], 1):
                if budget <= 0:
                    break
                img = None
                for v in (u, u.split("?")[0] + "?impolicy=SEO-BROCHURE-BOX-VIEWER"):
                    try:
                        img = _get(v, binaire=True)
                        break
                    except Exception:
                        continue
                if not img:
                    bilan["erreurs"].append(f"{ens} page {i} : image refusée")
                    continue
                budget -= 1
                bilan["pages"] += 1
                for p in lire_page(img, ens):
                    if not isinstance(p, dict) or not isinstance(p.get("prix"), (int, float)) or p["prix"] < 15:
                        continue
                    if ALIMENTAIRE.search(f"{p.get('nom', '')} {p.get('marque', '')}"):
                        continue
                    p["valable_du"], p["valable_au"] = du or p.get("valable_du"), au or p.get("valable_au")  # dates de Bonial, plus sûres
                    nom = " ".join(x for x in (p.get("marque"), p.get("nom")) if x).strip()
                    nouveaux.append({"id": hashlib.sha1(f"{cid}{i}{nom}".encode()).hexdigest()[:10], "titre": nom[:160],
                                     "prix": float(p["prix"]), "prix_avant": p.get("prix_avant"), "remise_pct": p.get("remise_pct"),
                                     "valable_du": p.get("valable_du"), "valable_au": p.get("valable_au"), "conditions": p.get("conditions"),
                                     "marchand": ens.replace("-", " "), "prospectus": cid, "page": i,
                                     "lien": f"https://www.bonial.fr/Enseignes/{ens}", "vu": jour})
            if bilan["pages"]:  # marqué « lu » seulement si des pages ont vraiment été lues
                base["lus"][cid] = {"enseigne": ens, "jour": jour, "pages": min(len(urls), PAGES_MAX)}
    vus = set()
    def _cle(p):  # même produit lu deux fois (grille d'offres + page lue par Gemini)
        return re.sub(r"[^a-z0-9]", "", (p["titre"] or "").lower())[:40] + str(round(p["prix"]))
    nouveaux = [p for p in nouveaux if not (_cle(p) in vus or vus.add(_cle(p)))]
    bilan["produits"] = len(nouveaux)
    garder = [p for p in base["produits"] if (p.get("valable_au") or p.get("vu", "")) >= jour[:10] or p.get("vu", "") >= jour]
    base = {"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "bilan": bilan,
            "lus": dict(list(base["lus"].items())[-500:]), "produits": (garder + nouveaux)[-3000:]}
    os.makedirs(os.path.dirname(F_SORTIE), exist_ok=True)
    json.dump(base, open(F_SORTIE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return bilan


def annonces(maxi=200):
    """Les produits des prospectus au format des annonces (pour la veille et le passage)."""
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = []
    for p in _lire(F_SORTIE, {}).get("produits", []):
        if (p.get("valable_au") or "9999") < jour:
            continue
        out.append({"id": "prosp-" + p["id"], "titre": p["titre"] + (f" ({p['conditions']})" if p.get("conditions") else ""),
                    "temperature": int((p.get("remise_pct") or 0) * 8), "categorie": "", "marchand": p["marchand"], "prix": p["prix"],
                    "devise": "EUR", "lien": p["lien"], "date": p.get("vu", jour), "source": "prospectus", "pays": "FR",
                    "description": (f"prix avant {p['prix_avant']} €. " if p.get("prix_avant") else "")
                                   + f"en magasin, valable {p.get('valable_du') or '?'} → {p.get('valable_au') or '?'}"})
    return out[-maxi:]


if __name__ == "__main__":
    import sys
    print(tour(sys.argv[1:] or ["Lidl"], pages_jour=int(os.environ.get("PAGES", "6"))))
