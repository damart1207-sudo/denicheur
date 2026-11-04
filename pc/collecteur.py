"""COLLECTEUR PC (accord de David du 04/11/2026) : lit depuis le PC de David, avec son navigateur et ses comptes, les pages
que le cloud ne peut pas lire (Fnac, Darty, Boulanger, Cdiscount, Decathlon, Leroy Merlin, ManoMano, But, Conforama, Adidas,
Back Market, Intersport, Zalando outlet, ventes privées Veepee / Showroomprivé / Zalando Privé / Privalia / BazarChic),
à rythme humain (une page toutes les quelques secondes, une fois par heure), puis pousse les annonces dans le dépôt
(data/pc/annonces.json) : les dénicheurs du cloud les lisent comme n'importe quelle source.

Installation (une fois, dans un terminal, dossier du dépôt cloné) :
    pip install playwright
    python -m playwright install chromium
    python pc/collecteur.py --connexion      -> ouvre le navigateur : se connecter à Veepee, Showroomprivé, Zalando Privé,
                                                Privalia, BazarChic, puis fermer la fenêtre (les connexions sont gardées)
    python pc/installer.py                   -> crée la tâche planifiée Windows « Denicheur collecteur » (toutes les heures, silencieuse)

Lancement manuel : python pc/collecteur.py          Aucun achat, aucune dépense.
"""
import argparse
import glob
import hashlib
import html as _html
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFIL = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Denicheur", "profil")
F_SORTIE = os.path.join(RACINE, "data", "pc", "annonces.json")
D_ECH = os.path.join(RACINE, "data", "echantillons", "pc")

PAGES = [
    ("fnac-bonsplans", "https://www.fnac.com/Bons-plans", "FR", "Fnac"),
    ("fnac-destockage", "https://www.fnac.com/destockage", "FR", "Fnac"),
    ("darty-bonsplans", "https://www.darty.com/nav/extra/bons_plans", "FR", "Darty"),
    ("darty-occasion", "https://www.darty.com/nav/extra/produits_occasion", "FR", "Darty"),
    ("boulanger-bonsplans", "https://www.boulanger.com/evt/bons-plans", "FR", "Boulanger"),
    ("boulanger-occasions", "https://www.boulanger.com/c/occasions", "FR", "Boulanger"),
    ("cdiscount-ventes-flash", "https://www.cdiscount.com/vente-flash", "FR", "Cdiscount"),
    ("cdiscount-bonsplans", "https://www.cdiscount.com/bons-plans", "FR", "Cdiscount"),
    ("decathlon-seconde-vie", "https://www.decathlon.fr/seconde-vie", "FR", "Decathlon"),
    ("decathlon-promos", "https://www.decathlon.fr/all-sports/promotions", "FR", "Decathlon"),
    ("leroymerlin-promos", "https://www.leroymerlin.fr/promotions/", "FR", "Leroy Merlin"),
    ("manomano-bonsplans", "https://www.manomano.fr/bons-plans", "FR", "ManoMano"),
    ("but-promos", "https://www.but.fr/promos/", "FR", "But"),
    ("conforama-promos", "https://www.conforama.fr/promos", "FR", "Conforama"),
    ("adidas-outlet", "https://www.adidas.fr/outlet", "FR", "Adidas"),
    ("intersport-promos", "https://www.intersport.fr/promotions/", "FR", "Intersport"),
    ("zalando-outlet", "https://www.zalando.fr/outlet/", "FR", "Zalando"),
    ("backmarket-bonsplans", "https://www.backmarket.fr/fr-fr/l/bons-plans/0d7f5f5d-1d84-4c1e-8d6a-cfa6f2f2b7b2", "FR", "Back Market"),
    ("veepee", "https://www.veepee.fr/gr/home/default", "FR", "Veepee"),
    ("showroomprive", "https://www.showroomprive.com/", "FR", "Showroomprivé"),
    ("zalando-prive", "https://www.zalando-prive.fr/", "FR", "Zalando Privé"),
    ("bazarchic", "https://www.bazarchic.com/", "FR", "BazarChic"),
    # --- ajoutés le 04/11 (David : « tous les sites, centres commerciaux compris ») ; les adresses qui répondent 404 sont retirées après la première collecte
    ("electrodepot-promos", "https://www.electrodepot.fr/promotions.html", "FR", "Electro Dépôt"),
    ("rueducommerce-promos", "https://www.rueducommerce.fr/promotions", "FR", "Rue du Commerce"),
    ("materielnet-promos", "https://www.materiel.net/promotions/", "FR", "Materiel.net"),
    ("topachat-promos", "https://www.topachat.com/pages/promos.php", "FR", "TopAchat"),
    ("cybertek-promos", "https://www.cybertek.fr/promotions.aspx", "FR", "Cybertek"),
    ("grosbill-promos", "https://www.grosbill.com/promotions", "FR", "Grosbill"),
    ("ubaldi-promos", "https://www.ubaldi.com/promotions/", "FR", "Ubaldi"),
    ("sonvideo-promos", "https://www.son-video.com/promotions", "FR", "Son-Vidéo"),
    ("cultura-bonsplans", "https://www.cultura.com/bons-plans.html", "FR", "Cultura"),
    ("micromania-occasion", "https://www.micromania.fr/occasion.html", "FR", "Micromania"),
    ("micromania-promos", "https://www.micromania.fr/promotions.html", "FR", "Micromania"),
    ("laredoute-outlet", "https://www.laredoute.fr/pplp/100/outlet.aspx", "FR", "La Redoute"),
    ("laredoute-promos", "https://www.laredoute.fr/pplp/100/promotions.aspx", "FR", "La Redoute"),
    ("carrefour-promos", "https://www.carrefour.fr/promotions", "FR", "Carrefour"),
    ("carrefour-destockage", "https://www.carrefour.fr/evenement/destockage", "FR", "Carrefour"),
    ("leclerc-promos", "https://www.e.leclerc/cat/promotions", "FR", "E.Leclerc"),
    ("auchan-promos", "https://www.auchan.fr/promotions", "FR", "Auchan"),
    ("lidl-offres", "https://www.lidl.fr/c/offres-en-ligne/s10008094", "FR", "Lidl"),
    ("action-offres", "https://www.action.com/fr-fr/offres/", "FR", "Action"),
    ("gifi-promos", "https://www.gifi.fr/promotions.html", "FR", "Gifi"),
    ("noz-arrivages", "https://www.noz.fr/", "FR", "Noz"),
    ("stokomani", "https://www.stokomani.fr/", "FR", "Stokomani"),
    ("centrakor-promos", "https://www.centrakor.com/promotions", "FR", "Centrakor"),
    ("foirfouille-promos", "https://www.lafoirfouille.fr/promotions", "FR", "La Foir'Fouille"),
    ("maisonsdumonde-promos", "https://www.maisonsdumonde.com/FR/fr/promotions", "FR", "Maisons du Monde"),
    ("castorama-promos", "https://www.castorama.fr/promotions/", "FR", "Castorama"),
    ("bricodepot-arrivages", "https://www.bricodepot.fr/arrivages/", "FR", "Brico Dépôt"),
    ("norauto-promos", "https://www.norauto.fr/promotions.html", "FR", "Norauto"),
    ("feuvert-promos", "https://www.feuvert.fr/promotions", "FR", "Feu Vert"),
    ("jardiland-promos", "https://www.jardiland.com/promotions", "FR", "Jardiland"),
    ("truffaut-promos", "https://www.truffaut.com/promotions", "FR", "Truffaut"),
    ("kiabi-promos", "https://www.kiabi.com/promotions", "FR", "Kiabi"),
    ("jules-promos", "https://www.jules.com/fr-fr/c/promotions", "FR", "Jules"),
    ("puma-outlet", "https://fr.puma.com/fr/fr/outlet", "FR", "Puma"),
    ("newbalance-outlet", "https://www.newbalance.fr/fr/outlet/", "FR", "New Balance"),
    ("asics-outlet", "https://www.asics.com/fr/fr-fr/outlet/", "FR", "Asics"),
    ("underarmour-outlet", "https://www.underarmour.fr/fr-fr/c/outlet/", "FR", "Under Armour"),
    ("jdsports-promos", "https://www.jdsports.fr/promotions/", "FR", "JD Sports"),
    ("footlocker-promos", "https://www.footlocker.fr/fr/category/promotions.html", "FR", "Foot Locker"),
    ("sephora-bonsplans", "https://www.sephora.fr/bons-plans/", "FR", "Sephora"),
    ("nocibe-promos", "https://www.nocibe.fr/promotions", "FR", "Nocibé"),
    ("marionnaud-promos", "https://www.marionnaud.fr/promotions", "FR", "Marionnaud"),
    ("easycash-occasion", "https://www.easycash.fr/", "FR", "Easy Cash"),
    ("cashconverters", "https://www.cashconverters.fr/", "FR", "Cash Converters"),
    ("amazon-warehouse", "https://www.amazon.fr/s?i=warehouse-deals&rh=n%3A13921051", "FR", "Amazon Seconde main"),
    ("amazon-outlet", "https://www.amazon.fr/outlet", "FR", "Amazon Outlet"),
    ("rakuten-flash", "https://fr.shopping.rakuten.com/event/ventes-flash", "FR", "Rakuten"),
    ("bonial-catalogues", "https://www.bonial.fr/", "FR", "Bonial (catalogues magasins)"),
    ("tiendeo-catalogues", "https://www.tiendeo.fr/", "FR", "Tiendeo (catalogues)"),
    ("idealo-promos", "https://www.idealo.fr/", "FR", "idealo"),
    # tendances : ce que le public cherche / achète en ce moment (lisible seulement depuis le PC : Amazon bloque le cloud)
    ("amazon-hausses-ventes", "https://www.amazon.fr/gp/movers-and-shakers/", "FR", "Amazon (hausses de ventes)"),
    ("amazon-plus-souhaites", "https://www.amazon.fr/gp/most-wished-for/", "FR", "Amazon (plus souhaités)"),
    ("amazon-nouveautes", "https://www.amazon.fr/gp/new-releases/", "FR", "Amazon (nouveautés)"),
    ("amazon-de-hausses", "https://www.amazon.de/gp/movers-and-shakers/", "DE", "Amazon DE (hausses de ventes)"),
    ("amazon-com-hausses", "https://www.amazon.com/gp/movers-and-shakers/", "US", "Amazon US (hausses de ventes)"),
    ("tiktok-top-produits", "https://ads.tiktok.com/business/creativecenter/top-products/pc/fr", "FR", "TikTok (top produits)"),
    ("leboncoin-tendances", "https://www.leboncoin.fr/", "FR", "Leboncoin (recherches populaires)"),
    ("vinted-tendances", "https://www.vinted.fr/", "FR", "Vinted (tendances)"),
    ("jd-classement", "https://top.jd.com/", "CN", "JD.com (classement des ventes)"),
    ("jd-phb", "https://www.jd.com/phb/", "CN", "JD.com (classement des ventes)"),
]
PRIX = re.compile(r"(\d{1,4}(?:[  ]\d{3})?[,.]\d{2})\s?€")


def _num(t):
    try:
        return round(float(t.replace(" ", "").replace(" ", "").replace(",", ".")), 2)
    except (ValueError, AttributeError):
        return None


def extraire_jd(h, source, marchand):
    """Classement JD.com : produits dans l'ordre de la page (liens item.jd.com/<n>.html), titre, prix en yuans s'il est là."""
    out, vus = [], set()
    for m in re.finditer(r'href="(?:https?:)?//item\.jd\.com/(\d+)\.html"[^>]*>(.{0,1500}?)</a>', h, re.S):
        sku = m.group(1)
        if sku in vus:
            continue
        bloc = m.group(2)
        t = re.search(r'title="([^"]{6,200})"', m.group(0)) or re.search(r'alt="([^"]{6,200})"', bloc)
        texte = t.group(1) if t else re.sub(r"<[^>]+>", " ", bloc)
        texte = " ".join(_html.unescape(texte).split())[:160]
        if len(texte) < 6:
            continue
        p = re.search(r'[¥￥]\s*(\d+(?:\.\d+)?)', h[m.end():m.end() + 1500])
        vus.add(sku)
        out.append({"id": hashlib.sha1(("jd" + sku).encode()).hexdigest()[:10], "titre": texte, "temperature": 0, "categorie": "classement",
                    "marchand": marchand, "prix": float(p.group(1)) if p else None, "devise": "CNY", "lien": f"https://item.jd.com/{sku}.html",
                    "date": datetime.now().strftime("%Y-%m-%dT%H:%M"), "source": "pc:" + source, "pays": "CN", "description": "", "rang": len(out) + 1})
    return out[:50]


def extraire(h, source, pays, marchand, url_base):
    """Produits de la page : JSON-LD schema.org (Product / ItemList / offers) d'abord, puis blocs HTML avec prix et lien."""
    if source.startswith("jd-"):
        return extraire_jd(h, source, marchand)
    out = []
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue

        def visiter(o):
            if isinstance(o, dict):
                offres = o.get("offers")
                if o.get("@type") in ("Product", "ProductGroup") and offres:
                    offre = offres[0] if isinstance(offres, list) else offres
                    prix = _num(str(offre.get("price") or offre.get("lowPrice") or ""))
                    lien = o.get("url") or offre.get("url") or ""
                    if prix and o.get("name"):
                        out.append((o["name"], prix, lien if lien.startswith("http") else url_base + lien, None, (o.get("brand") or {}).get("name") if isinstance(o.get("brand"), dict) else o.get("brand")))
                for v in o.values():
                    visiter(v)
            elif isinstance(o, list):
                for v in o:
                    visiter(v)
        visiter(d)
    if not out:  # secours : chaque lien de produit avec un prix dans les 600 caractères qui suivent
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.{0,600}?)(?=<a |$)', h, re.S):
            texte = _html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).strip()
            prix = PRIX.findall(m.group(3)) or PRIX.findall(m.group(2))
            if len(texte) < 12 or not prix:
                continue
            p = _num(prix[0])
            if p and 5 <= p <= 3000:
                lien = m.group(1)
                out.append((texte[:160], p, lien if lien.startswith("http") else url_base + lien, _num(prix[1]) if len(prix) > 1 else None, None))
    annonces, vus = [], set()
    for titre, prix, lien, prix2, marque in out:
        ident = hashlib.sha1(lien.encode()).hexdigest()[:10]
        if ident in vus:
            continue
        vus.add(ident)
        initial = max(prix, prix2) if prix2 and prix2 > prix else None
        remise = round((1 - prix / initial) * 100) if initial else None
        annonces.append({"id": ident, "titre": titre[:180], "temperature": (remise or 0) * 8, "categorie": "", "marchand": marchand,
                         "prix": prix, "devise": "EUR", "lien": lien, "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
                         "source": "pc:" + source, "pays": pays, "description": (f"prix initial {initial} €, -{remise} %. " if remise else "") + (f"marque {marque}" if marque else "")})
    return annonces


def collecter(connexion=False):
    from playwright.sync_api import sync_playwright
    os.makedirs(PROFIL, exist_ok=True)
    os.makedirs(D_ECH, exist_ok=True)
    resultats, etat = [], {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFIL, channel="chrome", headless=not connexion, locale="fr-FR", viewport={"width": 1366, "height": 900},
                                                   args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if connexion:
            for s in ("https://www.veepee.fr/", "https://www.showroomprive.com/", "https://www.zalando-prive.fr/", "https://www.bazarchic.com/"):
                try:
                    page = ctx.new_page()  # un onglet par site : évite « navigation interrompue » (redirections)
                    page.goto(s, wait_until="commit", timeout=60000)
                except Exception as e:
                    print("(chargement lent, ce n'est pas grave :", type(e).__name__, ")")
                print(f"Connecte-toi sur {s} puis appuie sur Entrée ici (ou Entrée seul pour passer).")
                input()
            ctx.close()
            print("Connexions gardées dans", PROFIL)
            return
        for source, url, pays, marchand in PAGES:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500 + random.randint(0, 2500))
                for _ in range(3):  # faire défiler : charge les produits des pages à chargement progressif
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(700)
                h = page.content()
                base = re.match(r"https?://[^/]+", url).group(0)
                ann = extraire(h, source, pays, marchand, base)
                etat[source] = {"ok": True, "nb": len(ann), "taille": len(h)}
                resultats += ann
                # copie pour le cloud : compressée et nettoyée des clés/jetons que les sites laissent dans leurs pages
                # (sinon GitHub refuse l'envoi : « push declined due to repository rule violations »)
                import gzip
                propre = re.sub(r"AIza[0-9A-Za-z_\-]{30,}|(?:sk|pk|rk)_(?:live|test)_[0-9A-Za-z]{10,}|eyJ[0-9A-Za-z_\-]{20,}\.[0-9A-Za-z_\-.]{20,}|[0-9A-Za-z_\-]{40,}",
                                "X", h[:1500000])
                with gzip.open(os.path.join(D_ECH, source + ".html.gz"), "wt", encoding="utf-8") as f:
                    f.write(propre)
            except Exception as e:
                etat[source] = {"ok": False, "erreur": f"{type(e).__name__}: {str(e)[:120]}"}
            print(source, etat[source])
            time.sleep(3 + random.random() * 5)
        ctx.close()
    os.makedirs(os.path.dirname(F_SORTIE), exist_ok=True)
    anciens = []
    try:
        anciens = json.load(open(F_SORTIE, encoding="utf-8")).get("annonces", [])
    except (OSError, json.JSONDecodeError):
        pass
    vus = {a["id"] for a in resultats}
    limite = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    garde = [a for a in anciens if a["id"] not in vus and a.get("date", "")[:10] >= limite]
    json.dump({"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "etat": etat, "annonces": (garde + resultats)[-3000:]},
              open(F_SORTIE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{len(resultats)} annonces lues -> {F_SORTIE}")
    return resultats


def pousser():
    """git pull + commit + push (identifiants Git du PC). Jamais bloquant : si ça échoue, on réessaie à l'heure suivante."""
    def git(*a):
        return subprocess.run(["git", "-C", RACINE, *a], capture_output=True, text=True, timeout=120)
    git("fetch", "-q", "origin", "main")
    git("reset", "-q", "--soft", "origin/main")   # oublie un envoi raté précédent (ex. page brute refusée par GitHub)
    git("reset", "-q")
    for vieux in glob.glob(os.path.join(D_ECH, "*.html")):  # anciennes pages brutes non nettoyées : jamais envoyées
        os.remove(vieux)
    git("add", "-A", "data/pc", "data/echantillons/pc")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return "rien de nouveau"
    git("commit", "-q", "-m", "Collecteur PC " + datetime.now().strftime("%d/%m %H:%M"))
    r = git("push", "-q", "origin", "HEAD:main")
    return "poussé" if r.returncode == 0 else "push impossible : " + r.stderr[-200:]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--connexion", action="store_true", help="ouvrir le navigateur pour se connecter aux ventes privées (une fois)")
    ap.add_argument("--sans-push", action="store_true")
    a = ap.parse_args()
    if a.connexion:
        collecter(connexion=True)
    else:
        collecter()
        if not a.sans_push:
            print(pousser())
