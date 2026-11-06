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
    ("manomano-bonsplans", "https://www.manomano.fr/", "FR", "ManoMano"),
    ("manomano-blackfriday", "https://www.manomano.fr/", "FR", "ManoMano"),
    ("cdiscount-meilleures-offres", "https://www.cdiscount.com/", "FR", "Cdiscount"),
    ("rakuten-meilleures-offres", "https://fr.shopping.rakuten.com/", "FR", "Rakuten"),
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
    ("ledenicheur-bonsplans", "https://ledenicheur.fr/bons-plans", "FR", "LeDénicheur (baisses de prix)"),
    ("interencheres", "https://www.interencheres.com/", "FR", "Interenchères (enchères)"),
    ("agorastore", "https://www.agorastore.fr/", "FR", "Agorastore (enchères)"),
    ("encheres-domaine", "https://encheres-domaine.gouv.fr/", "FR", "Enchères du Domaine (État)"),
    ("rakuten-occasion", "https://fr.shopping.rakuten.com/", "FR", "Rakuten"),
    ("kingjouet-promos", "https://www.king-jouet.com/promotions/", "FR", "King Jouet"),
    ("joueclub-promos", "https://www.joueclub.fr/promotions.html", "FR", "JouéClub"),
    ("stockx-populaires", "https://stockx.com/fr-fr", "FR", "StockX"),
    ("labelemmaus", "https://www.label-emmaus.co/fr/", "FR", "Label Emmaüs"),
    ("rebuy", "https://www.rebuy.fr/", "FR", "Rebuy"),
    ("jd-classement", "https://top.jd.com/", "CN", "JD.com (classement des ventes)"),
    ("jd-rank-m", "https://ranking.m.jd.com/", "CN", "JD.com (classement des ventes)"),
    ("jd-rank-pc", "https://www.jd.com/rank/", "CN", "JD.com (classement des ventes)"),
    ("smzdm-top", "https://www.smzdm.com/top/", "CN", "SMZDM (classement)"),
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
    for m in re.finditer(r'href="(?:https?:)?//item(?:\.m)?\.jd\.com/(?:product/)?(\d+)\.html[^"]*"[^>]*>(.{0,1500}?)</a>', h, re.S):
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


def extraire_json_integre(h, source, pays, marchand, url_base):
    """Les produits tels que le site les a envoyés à la page (données __NEXT_DATA__ / état initial) : prix en NOMBRES,
    jamais lus à l'écran. ManoMano : price.currentPrice.amountWithVat, retailPrice (« le + bas sur 30 j »), vendeur,
    isSecondHand. Le lien est retrouvé grâce à l'image de la carte (alt = titre)."""
    out = []
    for m in re.finditer(r'<script[^>]*id="(?:__NEXT_DATA__|__NUXT_DATA__)"[^>]*>(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        pile = [d]
        while pile:
            o = pile.pop()
            if isinstance(o, list):
                pile += o
                continue
            if not isinstance(o, dict):
                continue
            pile += [v for v in o.values() if isinstance(v, (dict, list))]
            titre = o.get("title") or o.get("name")
            px = o.get("price")
            if not isinstance(titre, str) or not isinstance(px, dict):
                continue
            cur = (px.get("currentPrice") or {}).get("amountWithVat") if isinstance(px.get("currentPrice"), dict) else px.get("amount") or px.get("value")
            ret = (px.get("retailPrice") or {}).get("amountWithVat") if isinstance(px.get("retailPrice"), dict) else None
            if not isinstance(cur, (int, float)) or cur <= 0:
                continue
            out.append({"titre": titre.strip(), "prix": float(cur), "initial": float(ret) if isinstance(ret, (int, float)) and ret > cur else None,
                        "occasion": bool(o.get("isSecondHand")), "vendeur": (o.get("seller") or {}).get("name") if isinstance(o.get("seller"), dict) else None,
                        "marque": (o.get("brand") or {}).get("name") if isinstance(o.get("brand"), dict) else None,
                        "remise": px.get("discountPercentage"), "note": (o.get("productRating") or {}).get("average") if isinstance(o.get("productRating"), dict) else None})
    if not out:
        return []
    def lien_de(titre):  # le lien produit le plus proche AVANT l'image de la carte (alt = titre)
        for t in (_html.escape(titre, quote=True), titre):
            i = h.find('alt="' + t)
            if i > 0:
                avant = h[max(0, i - 6000):i]
                ls = re.findall(r'href="((?:https?://[^"/]+)?/p/[^"]+|(?:https?://[^"/]+)?/[^"]*?(?:produit|product|/fp/|/dp/)[^"]+)"', avant)
                if ls:
                    return _html.unescape(ls[-1])
        return ""
    annonces, vus = [], set()
    for p in out:
        lien = lien_de(p["titre"])
        lien = lien if lien.startswith("http") else (url_base + lien if lien else "")
        if not lien or lien in vus:
            continue
        vus.add(lien)
        remise = round((1 - p["prix"] / p["initial"]) * 100) if p["initial"] else None
        annonces.append({"id": hashlib.sha1(lien.encode()).hexdigest()[:10], "titre": p["titre"][:180], "temperature": (remise or 0) * 8,
                         "categorie": "", "marchand": marchand + (f" (vendeur {p['vendeur']})" if p.get("vendeur") else ""), "prix": p["prix"],
                         "devise": "EUR", "lien": lien, "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "source": "pc:" + source,
                         "pays": pays, "etat": "occasion" if p["occasion"] else "neuf", "prix_source": "donnees_integrees",
                         "description": (f"prix initial {p['initial']} €, -{remise} %. " if remise else "") + (f"marque {p['marque']}. " if p.get("marque") else "")
                                        + ("OCCASION. " if p["occasion"] else "") + (f"note {p['note']}/5" if p.get("note") else "")})
    return annonces


def extraire(h, source, pays, marchand, url_base):
    """Produits de la page : JSON-LD schema.org (Product / ItemList / offers) d'abord, puis blocs HTML avec prix et lien."""
    if source.startswith("jd-"):
        return extraire_jd(h, source, marchand)
    integre = extraire_json_integre(h, source, pays, marchand, url_base)  # données chiffrées de la page : toujours en premier
    if len(integre) >= 3:
        return integre
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

JS_CARTES = r"""
() => {
  const PRIX = /(\d{1,3}(?:[\s\u00a0\u202f.]\d{3})*(?:[,.]\d{1,2})?)\s?(?:€|EUR)|(?:€)\s?(\d{1,3}(?:[\s\u00a0\u202f.]\d{3})*(?:[,.]\d{1,2})?)/g;
  const num = t => { if (!t) return null; t = t.replace(/[\s\u00a0\u202f]/g, '');
    if (/\.\d{3}(?!\d)/.test(t) && !/,/.test(t)) t = t.replace(/\./g, ''); t = t.replace(',', '.'); const v = parseFloat(t); return isNaN(v) ? null : v; };
  const vus = new Set(), out = [];
  const T = e => (e.textContent || '').replace(/\s+/g, ' ').trim();
  const feuilles = [...document.querySelectorAll('body *')].filter(e => e.children.length <= 2 && !e.closest('nav,header,footer,[role=navigation],[class*=menu]') && /\d/.test(e.textContent) && /€|EUR/.test(e.textContent) && T(e).length < 40);
  for (const f of feuilles) {
    let c = f, carte = null;
    for (let i = 0; i < 7 && c; i++) { c = c.parentElement; if (c && c.querySelector('a[href]') && c.querySelector('img,picture,[style*=background-image]') && T(c).length < 900) { carte = c; break; } }
    if (!carte) continue;
    const a = [...carte.querySelectorAll('a[href]')].find(x => !/panier|cart|wishlist|compare|login|#/.test(x.getAttribute('href') || '')) || carte.querySelector('a[href]');
    const lien = a ? a.href : null;
    if (!lien || vus.has(lien)) continue;
    const img = carte.querySelector('img');
    const titres = [...carte.querySelectorAll('[class*=name],[class*=title],[class*=titre],[class*=libelle],h3,h4,h2')].map(x => T(x)).filter(t => t.length > 8 && t.length < 200);
    let titre = (img && img.alt && img.alt.length > 8 ? img.alt : '') || titres[0] || (a && (a.title || T(a))) || '';
    titre = titre.replace(/\s+/g, ' ').trim();
    if (titre.length < 8 || /voir tout|€|livraison offerte|coups? de c|ajouter au panier/i.test(titre)) continue;
    const prix = [];
    for (const m of T(f).matchAll(PRIX)) { const v = num(m[1] || m[2]); if (v && v >= 3 && v <= 20000) prix.push(v); }  // le prix affiché, pas les mensualités
    if (!prix.length || /mois|\/m|par m|x\s?\d|dès/i.test(T(f))) continue;
    vus.add(lien);
    const barre = [...carte.querySelectorAll('s,del,[class*=strike],[class*=barre],[class*=old],[class*=crossed]')].map(x => num((x.textContent.match(/[\d\s\u00a0.,]+/) || [''])[0])).filter(v => v);
    out.push({titre: titre.slice(0, 180), prix: prix[0], initial: barre.length ? Math.max(...barre) : null, lien});
    if (out.length >= 300) break;
  }
  return out;
}
"""
MOTS_PROMO = re.compile(r"bons?[\s-]*plans?|promo|destockage|déstockage|black\s*friday|soldes|outlet|offres?\s+du\s+moment|ventes?\s+flash", re.I)


def statut_page(h):
    """Bloqué par une protection anti-robot ? page introuvable ? (pour le tri des sites)"""
    t = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", h[:300000], flags=re.S))
    if re.search(r"Accès bloqué|Access denied|WAF Block|Vérifions ensemble que vous n.êtes pas un robot|Enable JavaScript and cookies to continue|captcha|site n'est actuellement pas disponible", t, re.I):
        return "bloqué"
    if re.search(r"\b404\b|Page introuvable|page n'existe pas|Not Found", t[:3000], re.I):
        return "introuvable"
    return "ok"


# Méthode de David (05/11) : depuis l'accueil, cliquer l'onglet « Nos meilleures offres » / « Black Friday » et faire défiler.
SUIVRE = {"manomano-bonsplans": r"meilleures offres", "manomano-blackfriday": r"black\s*friday",
          "cdiscount-meilleures-offres": r"meilleures offres|black\s*friday|bons plans|promos?",
          "rakuten-meilleures-offres": r"meilleures offres|black\s*friday|bons plans|promos?"}
DEFILEMENTS_LONGS = 18   # pages de meilleures offres : beaucoup de produits chargés au fil du défilement


def decouvrir_page_promo(page, url, motif=None):
    """On part de l'accueil du site et on suit le lien « meilleures offres / bons plans / promos / Black Friday »."""
    base = re.match(r"https?://[^/]+", url).group(0)
    page.goto(base + "/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)
    liens = page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.textContent.trim().slice(0, 60), a.href])")
    rx = re.compile(motif, re.I) if motif else MOTS_PROMO
    domaine = base.split("//")[1].replace("www.", "")
    for texte, lien in liens:
        if domaine in lien and rx.search(texte or ""):
            return lien
    return None


def cartes_vers_annonces(cartes, source, pays, marchand):
    out = []
    for c in cartes or []:
        if not c.get("lien") or not c.get("prix"):
            continue
        initial = c.get("initial") if c.get("initial") and c["initial"] > c["prix"] else None
        remise = round((1 - c["prix"] / initial) * 100) if initial else None
        out.append({"id": hashlib.sha1(c["lien"].encode()).hexdigest()[:10], "titre": c["titre"][:180], "temperature": (remise or 0) * 8,
                    "categorie": "", "marchand": marchand, "prix": round(c["prix"], 2), "devise": "EUR", "lien": c["lien"],
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "source": "pc:" + source, "pays": pays,
                    "description": f"prix initial {initial} €, -{remise} %." if remise else ""})
    return out


JS_PRIX_FICHE = r"""
() => {
  const T = e => (e.textContent || '').replace(/\s+/g, ' ').trim();
  const h1 = document.querySelector('h1');
  const cands = [...document.querySelectorAll('[itemprop=price],[class*=price],[data-testid*=price],[class*=Price]')]
     .filter(e => !e.closest('s,del,[class*=strike],[class*=old],[class*=crossed],nav,header,footer,[class*=similar],[class*=recommend],[class*=carousel]'))
     .filter(e => /\d/.test(T(e)) && /€/.test(T(e)) && T(e).length < 25);
  if (!cands.length) return null;
  // le prix le plus gros affiché, le plus proche du titre
  let best = null, bestScore = -1;
  for (const e of cands) {
    const fs = parseFloat(getComputedStyle(e).fontSize) || 0;
    const d = h1 ? Math.abs(e.getBoundingClientRect().top - h1.getBoundingClientRect().top) : 0;
    const score = fs * 10 - d / 50;
    if (score > bestScore) { bestScore = score; best = e; }
  }
  const t = T(best).replace(/[\s\u00a0\u202f]/g, '');
  const m = t.match(/(\d+(?:[.,]\d{3})*)(?:[.,](\d{1,2}))?€/);
  if (!m) return null;
  return parseFloat(m[1].replace(/[.,]/g, '') + '.' + (m[2] || '0'));
}
"""
VERIF_MAX = 25        # fiches produit relues par tour (les plus fortes remises d'abord)
VERIF_REMISE_MIN = 30  # % : on relit la fiche des produits remisés d'au moins 30 %


def verifier_fiches(page, annonces):
    """Relit la fiche avec le contrôle strict du produit et de son offre en stock.
    Corrige le prix si la carte a été mal lue ; marque prix_verifie (True/False). Incident Makita LS1019L du 05/11."""
    sys.path.insert(0, RACINE)
    from denicheur.verif_prix import prix_officiel
    def remise(a):
        m = re.search(r"-(\d+) %", a.get("description") or "")
        return int(m.group(1)) if m else 0
    cibles = sorted([a for a in annonces if remise(a) >= VERIF_REMISE_MIN and a.get("lien", "").startswith("http")], key=lambda a: -remise(a))[:VERIF_MAX]
    for a in cibles:
        try:
            page.goto(a["lien"], wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(2500 + random.randint(0, 1500))
            p = prix_officiel(page.content(), a["lien"], [a.get("ean"), a.get("sku")])
            if page.url != a["lien"]:
                p = None
        except Exception:
            p = None
        if not p:
            a["prix_verifie"] = False
            continue
        a["preuve_prix"] = {"prix_page": p, "lien": a["lien"], "devise": "EUR",
                            "disponibilite": "InStock", "identite_confirmee": True,
                            "verifie_le": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        a["prix_page"] = p
        if abs(p - a["prix"]) <= 0.011:
            a["prix_verifie"] = True
        else:
            a["prix_carte"], a["prix"] = a["prix"], p
            a["prix_verifie"] = True
            a["description"] = (a.get("description") or "") + f" (prix corrigé sur la fiche : {p} €, carte lue {a['prix_carte']} €)"
        time.sleep(1 + random.random() * 2)
    return len(cibles)


def liberer_profil(profil):
    """Ferme les Chrome du robot restés ouverts sur CE profil (tour planté, fenêtre de connexion oubliée).
    Ton Chrome personnel n'est jamais touché (autre profil)."""
    if os.name != "nt":
        return
    motif = "*" + profil.replace("'", "") + " --*"
    ps = ("Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -like '" + motif + "' } "
          "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60)
    for verrou in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        try:
            os.remove(os.path.join(profil, verrou))
        except OSError:
            pass
    print("anciens navigateurs du robot fermés")


def collecter(connexion=False, seulement=None):
    from playwright.sync_api import sync_playwright
    os.makedirs(PROFIL, exist_ok=True)
    os.makedirs(D_ECH, exist_ok=True)
    resultats, etat = [], {}
    with sync_playwright() as p:
        for essai in range(6):  # profil occupé (un autre tour encore ouvert) : Chrome sort avec le code 21 -> on attend et on réessaie
            try:
                ctx = p.chromium.launch_persistent_context(PROFIL, channel="chrome", headless=False, locale="fr-FR", viewport={"width": 1366, "height": 900},
                                                           args=["--disable-blink-features=AutomationControlled"]
                                                           + ([] if connexion else ["--window-position=-32000,-32000"]))  # fenêtre hors écran : invisible pour toi
                break
            except Exception as e:
                if essai == 5:
                    raise
                print("navigateur occupé, nouvel essai dans 1 minute…", type(e).__name__)
                if essai == 1:
                    liberer_profil(PROFIL)
                time.sleep(60)
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
        for source, url, pays, marchand in [p for p in PAGES if not seulement or p[0] in seulement]:
            try:
                if source in SUIVRE:  # aller sur l'onglet « meilleures offres » comme un visiteur
                    cible = decouvrir_page_promo(page, url, SUIVRE[source])
                    url = cible or url
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:  # attendre que les produits chargés après coup soient arrivés
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(2000 + random.randint(0, 2000))
                for _ in range(DEFILEMENTS_LONGS if source in SUIVRE else 6):  # faire défiler : charge les produits progressifs
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(900)
                h = page.content()
                statut = statut_page(h)
                if statut == "bloqué":  # protection anti-robot qui vérifie : on lui laisse le temps (comme un humain)
                    page.wait_for_timeout(12000)
                    h = page.content()
                    statut = statut_page(h)
                if statut == "introuvable" and not source.startswith(("jd-", "amazon")):
                    nouvelle = decouvrir_page_promo(page, url)
                    if nouvelle:
                        page.goto(nouvelle, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(3000)
                        for _ in range(3):
                            page.mouse.wheel(0, 2500)
                            page.wait_for_timeout(700)
                        h = page.content()
                        statut = statut_page(h) + " (adresse trouvée : " + nouvelle[:80] + ")"
                base = re.match(r"https?://[^/]+", url).group(0)
                ann = extraire(h, source, pays, marchand, base)
                if len(ann) < 5 and statut.startswith("ok") and not source.startswith("jd-"):
                    try:  # lecture des cartes produit directement dans la page affichée
                        cartes = page.evaluate(JS_CARTES)
                        ann2 = cartes_vers_annonces(cartes, source, pays, marchand)
                        if len(ann2) > len(ann):
                            ann = ann2
                    except Exception:
                        pass
                etat[source] = {"ok": True, "nb": len(ann), "taille": len(h), "statut": statut}
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
        try:
            etat["fiches_verifiees"] = verifier_fiches(page, resultats)
        except Exception as e:
            etat["fiches_verifiees"] = f"erreur {type(e).__name__}"
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
    git("checkout", "origin/main", "--", "pc", "config")  # mise à jour automatique du code du PC (appliquée au tour suivant)
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
    ap.add_argument("--seulement", default="", help="liste de sources séparées par des virgules (test rapide)")
    a = ap.parse_args()
    if a.connexion:
        collecter(connexion=True)
    else:
        collecter(seulement=[x.strip() for x in a.seulement.split(",") if x.strip()] or None)
        if not a.sans_push:
            print(pousser())
