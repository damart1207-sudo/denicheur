"""Lecture AUTOMATIQUE de la page de chaque bon plan, par le robot (GitHub), au moment où l'alerte naît
puis à chaque tour tant qu'elle n'est pas vérifiée. Résultat dans l'alerte, champ « page_offre ».

But : Claude n'a plus jamais à écrire « page non lue » : ce que la page dit (prix, expiré ou pas, marchand, livraison,
code promo, stock) est déjà dans data/alertes.json quand il vérifie. Trois lectures, de la plus sûre à la moins sûre :
  1. le bon plan lui-même (sites Pepper : Dealabs, Chollometro, hotukdeals, mydealz, Pepper PL/NL, Preisjäger) :
     page du deal lue en HTML, données du deal (expiré, prix, marchand, livraison, code) + lien de sortie vers le marchand ;
  2. l'article (Les Numériques, Clubic, Frandroid, 01net, Journal du Geek) : prix et lien marchand dans l'article ;
  3. la page du marchand (lien de sortie) : prix affiché (JSON-LD / balises), disponibilité, mots « livraison » ;
     certains marchands bloquent les robots (Amazon souvent, Fnac, Cdiscount) : on le note, et la fiche Keepa
     (déjà dans l'alerte) tient lieu de lecture d'Amazon.
Rythme humain : 3 requêtes au plus par offre, 20 s de délai chacune, jamais en masse.
"""
import html as _html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DELAI = 20
PEPPER = ("dealabs.com", "chollometro.com", "hotukdeals.com", "mydealz.de", "pepper.pl", "pepper.it", "pepper.nl", "preisjaeger.at", "pepper.com")
ARTICLES = ("lesnumeriques.com", "clubic.com", "frandroid.com", "01net.com", "journaldugeek.com")
MOTS_BLOCAGE = re.compile(r"captcha|access denied|accès refusé|are you a robot|automated access|verify you are human|robot check|cf-chl|attention required|please enable js", re.I)
MOTS_EXPIRE = re.compile(r"n'est malheureusement plus d'actualit|ya no est[áa] disponible|expired|abgelaufen|wygas[łl]|verlopen|deal expir|offre expir", re.I)
MOTS_LIVRAISON_FR = re.compile(r"livr\w* (?:en|vers la|en France|France métropolitaine)|expédi\w* (?:en|vers la) France|ships? to france|env[ií]o a francia|lieferung nach frankreich|livraison gratuite|livraison offerte|frais de port|frais de livraison|port gratuit|retrait (?:gratuit|en magasin)|point relais|click ?& ?collect", re.I)
MOTS_RUPTURE = re.compile(r"rupture de stock|indisponible|out of stock|agotado|sin stock|nicht verfügbar|ausverkauft|niet op voorraad|momentan[ée]ment indisponible|plus disponible|sold out|actuellement indisponible", re.I)
MOTS_STOCK = re.compile(r"en stock|in stock|disponible|available|auf lager|verfügbar|op voorraad|ajouter au panier|add to basket|add to cart|añadir a la cesta|in den warenkorb", re.I)
MOTS_CODE = re.compile(r"\b(?:code|coupon|voucher|bon)\b[^.\n]{0,40}?\b([A-Z0-9]{4,20})\b")
PRIX = re.compile(r"(\d{1,4}(?:[  .]\d{3})*(?:[,.]\d{2})?)\s*(?:€|EUR|£|zł|PLN)|(?:€|£)\s*(\d{1,4}(?:[,.]\d{3})*(?:[,.]\d{2})?)", re.I)


def _maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="minutes")


def _get(url, timeout=DELAI, octets=1500000, referer=None):
    """GET poli. Renvoie (code, url_finale, texte). Les erreurs HTTP renvoient leur code (403, 503…) sans lever."""
    entetes = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    if referer:
        entetes["Referer"] = referer
    req = urllib.request.Request(url, headers=entetes)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.geturl(), r.read(octets).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            corps = e.read(200000).decode("utf-8", "replace")
        except Exception:
            corps = ""
        return e.code, e.geturl() if hasattr(e, "geturl") else url, corps
    except Exception as e:
        return None, url, f"{type(e).__name__}: {str(e)[:120]}"


def _texte(h, n=100000):
    h = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", h))
    return re.sub(r"\s+", " ", t).strip()[:n]


def _nombre(s):
    if s is None:
        return None
    s = str(s).replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = float(s)
        return round(v, 2) if 0 < v < 100000 else None
    except ValueError:
        return None


def _ld_json(h):
    """Produits JSON-LD (schema.org) de la page : [(nom, prix, devise, disponibilité)]."""
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h or "", re.S | re.I):
        try:
            d = json.loads(_html.unescape(m.group(1)).strip())
        except json.JSONDecodeError:
            continue
        pile = [d]
        while pile:
            o = pile.pop()
            if isinstance(o, list):
                pile.extend(o)
            elif isinstance(o, dict):
                if str(o.get("@type", "")).lower() in ("product", "offer", "aggregateoffer"):
                    offres = o.get("offers") or o
                    offres = offres if isinstance(offres, list) else [offres]
                    for of in offres:
                        if not isinstance(of, dict):
                            continue
                        prix = _nombre(of.get("price") or of.get("lowPrice"))
                        if prix:
                            out.append({"nom": str(o.get("name") or "")[:120], "prix": prix, "devise": of.get("priceCurrency"),
                                        "disponibilite": str(of.get("availability") or "").split("/")[-1] or None})
                pile.extend(v for v in o.values() if isinstance(v, (dict, list)))
    return out


def _domaine(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _champ_json(h, cle):
    """Valeur d'un champ "cle":valeur dans le JSON incrusté d'une page (Pepper : data-vue3, Nuxt…)."""
    m = re.search(r'(?:\\?"|&quot;)%s(?:\\?"|&quot;)\s*:\s*(true|false|null|-?\d+(?:\.\d+)?|(?:\\?"|&quot;)(.*?)(?:\\?"|&quot;)[,}])' % re.escape(cle), h)
    if not m:
        return None
    if m.group(2) is not None:
        return _html.unescape(m.group(2)).replace('\\"', '"')
    v = m.group(1)
    if v in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[v]
    try:
        return int(v) if re.fullmatch(r"-?\d+", v) else float(v)
    except ValueError:
        return None


# ---------------------------------------------------------------- 1. deal Pepper
def _pepper(url, alerte):
    code, fin, h = _get(url)
    p = {"page_deal": {"code": code, "lu": bool(code == 200 and h)}}
    if code != 200 or not h:
        p["page_deal"]["erreur"] = (h or "")[:120] if code is None else f"HTTP {code}"
        return p
    hh = _html.unescape(h)
    texte = _texte(h, 6000)
    expire = _champ_json(h, "isExpired")
    if expire is None:
        expire = bool(MOTS_EXPIRE.search(texte[:3000]))
    p["expiree"] = bool(expire)
    prix = _champ_json(h, "price")
    p["prix_page"] = _nombre(prix) if prix not in (None, 0, "0", "") else None
    p["prix_ailleurs_annonce"] = _nombre(_champ_json(h, "nextBestPrice"))
    port = _champ_json(h, "shipping")
    if port is None:
        port = _champ_json(h, "shippingCost")
    p["port_page"] = _nombre(port) if port not in (None, "", "0", 0) else (0.0 if port in ("0", 0) else None)
    gratuit = _champ_json(h, "isFreeShipping")
    if gratuit is True:
        p["port_page"] = 0.0
    code_promo = _champ_json(h, "voucherCode")
    p["code_promo"] = code_promo or None
    m = re.search(r'(?:\\?"|&quot;)merchant(?:\\?"|&quot;)\s*:\s*\{[^}]*?(?:\\?"|&quot;)name(?:\\?"|&quot;)\s*:\s*(?:\\?"|&quot;)([^"&\\]+)', h)
    p["marchand_page"] = _html.unescape(m.group(1)) if m else None
    desc = re.search(r'(?:\\?"|&quot;)description(?:\\?"|&quot;)\s*:\s*(?:\\?"|&quot;)(.{20,2500}?)(?:\\?"|&quot;)\s*[,}]', h, re.S)
    p["description"] = _texte(_html.unescape(desc.group(1)).replace("\\n", " ").replace('\\"', '"'), 1200) if desc else texte[:800]
    # lien de sortie vers le marchand : /visit/threadmain/<id> (redirection)
    ident = _champ_json(h, "threadId") or (re.search(r"-(\d{5,9})(?:[/?#]|$)", url) or [None, None])[1]
    if ident:
        dom = urllib.parse.urlparse(fin or url).netloc
        time.sleep(1.5)
        sortie = _redirection(f"https://{dom}/visit/threadmain/{ident}", referer=url)
        if sortie and _domaine(sortie) and _domaine(sortie) not in dom:
            p["lien_marchand"] = sortie
    return p


def _redirection(url, referer=None):
    """Suit les redirections d'un lien de sortie et renvoie l'adresse finale (nettoyée des paramètres de suivi)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer or url}, method="GET")
        with urllib.request.urlopen(req, timeout=DELAI) as r:
            fin = r.geturl()
            r.read(1)
    except urllib.error.HTTPError as e:
        fin = e.geturl() if hasattr(e, "geturl") else url
    except Exception:
        return None
    if fin == url:
        return None
    # dérouler les redirections d'affiliation qui portent l'adresse cible en paramètre (url=, u=, ued=, murl=…)
    for _ in range(3):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(fin).query)
        cible = next((q[k][0] for k in ("url", "u", "ued", "murl", "dest", "destination", "r", "redirect", "to") if k in q and q[k][0].startswith("http")), None)
        if not cible:
            break
        fin = urllib.parse.unquote(cible)
    u = urllib.parse.urlparse(fin)
    if "amazon." in u.netloc:
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", u.path)
        if m:
            return f"https://{u.netloc}/dp/{m.group(1)}"
    propre = {k: v for k, v in urllib.parse.parse_qsl(u.query) if not re.match(r"utm_|tag$|aff|ref|clickid|cmp|gclid|fbclid|awc|dclid|epi|siteID|ranMID|ranEAID|ranSiteID|tduid|zanpid|sv1|sv_", k, re.I)}
    return urllib.parse.urlunparse(u._replace(query=urllib.parse.urlencode(propre), fragment=""))


# ---------------------------------------------------------------- 2. article
def _article(url, alerte):
    code, fin, h = _get(url)
    p = {"page_deal": {"code": code, "lu": bool(code == 200 and h)}}
    if code != 200 or not h:
        p["page_deal"]["erreur"] = (h or "")[:120] if code is None else f"HTTP {code}"
        return p
    texte = _texte(h, 20000)
    p["description"] = texte[:1200]
    prix = [_nombre(a or b) for a, b in PRIX.findall(texte[:8000])]
    prix = [x for x in prix if x]
    cible = alerte.get("prix")
    p["prix_page"] = cible if cible and any(abs(x - cible) < 0.011 for x in prix) else (prix[0] if prix else None)
    p["expiree"] = bool(MOTS_EXPIRE.search(texte[:5000]))
    # lien marchand : premier lien sortant vers une boutique (amazon, fnac, cdiscount, darty, boulanger, leclerc, rakuten, ...)
    liens = re.findall(r'href="(https?://[^"]+)"', h)
    boutiques = re.compile(r"amazon\.|fnac\.|cdiscount\.|darty\.|boulanger\.|e\.leclerc|rakuten\.|rueducommerce\.|ldlc\.|materiel\.net|pccomponentes\.|aliexpress\.|samsung\.com|apple\.com|nike\.com|decathlon\.|leroymerlin\.|castorama\.|manomano\.|but\.fr|conforama\.|auchan\.|carrefour\.|lidl\.|action\.com|zalando\.|asos\.|sarenza\.|courir\.|jd-sports|back ?market|ubaldi\.|son-video\.|cybertek\.|grosbill\.|topachat\.|alternate\.|galaxus\.|otto\.|mediamarkt\.|saturn\.|argos\.|currys\.|very\.|john ?lewis|ebay\.|vinted\.|leboncoin\.", re.I)
    for l in liens:
        d = _domaine(l)
        if d and boutiques.search(l) and not any(a in d for a in ARTICLES):
            p["lien_marchand"] = _redirection(l) or l
            break
    return p


# ---------------------------------------------------------------- 3. marchand
def _marchand(url, alerte, referer=None):
    time.sleep(1.5)
    code, fin, h = _get(url, referer=referer)
    m = {"lien": url, "code": code, "lu": False, "domaine": _domaine(fin or url)}
    if code is None:
        m["erreur"] = (h or "")[:120]
        return m
    texte = _texte(h, 60000)
    if code != 200 or len(texte) < 400 or MOTS_BLOCAGE.search(texte[:4000]) or MOTS_BLOCAGE.search(h[:6000]):
        m["erreur"] = f"HTTP {code}" if code != 200 else "page anti-robot (captcha)"
        m["bloque"] = True
        return m
    m["lu"] = True
    t = re.search(r"<title[^>]*>(.*?)</title>", h, re.S | re.I)
    m["titre"] = _texte(t.group(1), 160) if t else None
    ld = _ld_json(h)
    if ld:
        m["json_ld"] = ld[:4]
        m["prix"] = ld[0]["prix"]
        m["devise"] = ld[0].get("devise")
        if ld[0].get("disponibilite"):
            m["disponibilite"] = ld[0]["disponibilite"]
    if not m.get("prix"):
        og = re.search(r'(?:product:price:amount|og:price:amount|itemprop="price")[^>]*?content="([\d.,]+)"', h) or re.search(r'content="([\d.,]+)"[^>]*?(?:product:price:amount|itemprop="price")', h)
        if og:
            m["prix"] = _nombre(og.group(1))
        elif "amazon." in m["domaine"]:
            a = re.search(r'class="a-offscreen">\s*([\d.,  ]+)\s*€', h)
            m["prix"] = _nombre(a.group(1)) if a else None
    if not m.get("prix"):
        cible = alerte.get("prix")
        prix = [x for x in (_nombre(a or b) for a, b in PRIX.findall(texte[:15000])) if x]
        if cible and any(abs(x - cible) < 0.011 for x in prix):
            m["prix"] = cible
        elif prix:
            m["prix_vus"] = prix[:6]
    if not m.get("disponibilite"):
        if MOTS_RUPTURE.search(texte[:20000]):
            m["disponibilite"] = "rupture"
        elif MOTS_STOCK.search(texte[:20000]):
            m["disponibilite"] = "en stock (panier)"
    liv = MOTS_LIVRAISON_FR.findall(texte)
    if liv:
        m["livraison_mots"] = sorted(set(x.strip().lower() for x in liv))[:6]
        i = texte.lower().find(liv[0].lower())
        m["livraison_extrait"] = texte[max(0, i - 80):i + 160]
    m["extrait"] = texte[:700]
    return m


def livraison_france(p, alerte):
    """oui / non / inconnue : l'offre peut-elle être livrée en France ? (pays FR : oui par défaut)."""
    pays = (alerte.get("pays") or "").upper()
    m = p.get("marchand") or {}
    dom = (m.get("domaine") or _domaine(p.get("lien_marchand") or "") or "").lower()
    texte = " ".join(str(x) for x in (p.get("description"), m.get("livraison_extrait"), m.get("extrait")) if x).lower()
    if re.search(r"amazon\.(fr|de|es|it|nl|pl|com\.be)|aliexpress\.|pccomponentes\.(fr|com|pt|it)|galaxus\.|alternate\.|zalando\.|asos\.|nike\.com|samsung\.com|apple\.com|back ?market|ebay\.(fr|de|es|it)", dom):
        return "oui"  # marchands qui livrent la France (Amazon UE : vérifier le port, dit dans le commentaire)
    if re.search(r"livr\w* (?:en|vers la) france|ships? to france|env[ií]o a francia|lieferung nach frankreich|europe entière|toute l'europe|eu-wide|livraison internationale", texte):
        return "oui"
    if pays in ("FR", ""):
        return "oui"
    if re.search(r"argos\.|currys\.|very\.|john ?lewis|tesco\.|boots\.|mediamarkt\.(at|de)|saturn\.de|otto\.de|lidl\.(de|at|es|pl)|aldi|action\.com|carrefour\.es|elcorteingles|mediamarkt\.es|worten\.|allegro\.|x-kom|morele|bol\.com|coolblue", dom):
        return "non"  # magasins nationaux : pas de livraison en France
    if pays == "UK":
        return "non" if not re.search(r"international|worldwide|europe", texte) else "inconnue"
    return "inconnue"


def lire_offre(alerte):
    """Lit la page du bon plan puis celle du marchand. Ne lève jamais : les erreurs sont écrites dans le résultat."""
    url = alerte.get("lien") or ""
    dom = _domaine(url)
    p = {"lu_le": _maintenant(), "lien_deal": url}
    try:
        if any(d in dom for d in PEPPER):
            p.update(_pepper(url, alerte))
            p["type_page"] = "deal Pepper"
        elif any(d in dom for d in ARTICLES):
            p.update(_article(url, alerte))
            p["type_page"] = "article"
        elif url:
            p["type_page"] = "marchand direct"
            p["lien_marchand"] = url
        cible = p.get("lien_marchand")
        if cible:
            p["marchand"] = _marchand(cible, alerte, referer=url if cible != url else None)
            if p["marchand"].get("lu"):
                md = p["marchand"]
                if md.get("disponibilite") == "rupture":
                    p["expiree"] = True
                if md.get("prix") and alerte.get("prix") and md["prix"] > alerte["prix"] * 1.15 and not p.get("code_promo"):
                    p["prix_remonte"] = md["prix"]  # le marchand affiche désormais plus cher : l'offre est sans doute finie
    except Exception as e:
        p["erreur"] = f"{type(e).__name__}: {str(e)[:150]}"
    p["livraison_france"] = livraison_france(p, alerte)
    p["resume"] = resume(p, alerte)
    return p


def resume(p, alerte):
    """Une phrase en français, prête pour le commentaire du verdict (ce que le robot a lu, et quand)."""
    heure = p.get("lu_le", "")[11:16]
    morceaux = []
    pd = p.get("page_deal") or {}
    if pd.get("lu"):
        etat = "expirée" if p.get("expiree") else "active"
        s = f"page du bon plan lue à {heure} UTC : offre {etat}"
        if p.get("prix_page"):
            s += f", {p['prix_page']} affiché"
        if p.get("port_page") is not None:
            s += ", port " + ("gratuit" if p["port_page"] == 0 else f"{p['port_page']}")
        if p.get("code_promo"):
            s += f", code {p['code_promo']}"
        if p.get("marchand_page"):
            s += f", marchand {p['marchand_page']}"
        morceaux.append(s)
    elif pd:
        morceaux.append(f"page du bon plan illisible ({pd.get('erreur', '?')})")
    m = p.get("marchand") or {}
    if m.get("lu"):
        s = f"fiche {m.get('domaine')} lue"
        if m.get("prix"):
            s += f" : {m['prix']} {m.get('devise') or ''}".rstrip()
        if m.get("disponibilite"):
            s += f", {m['disponibilite']}"
        if m.get("livraison_mots"):
            s += ", livraison : " + ", ".join(m["livraison_mots"][:3])
        morceaux.append(s)
    elif m:
        morceaux.append(f"{m.get('domaine') or 'marchand'} refuse les robots ({m.get('erreur', '?')})" + (" ; fiche Amazon connue par Keepa" if alerte.get("keepa") and "amazon" in (m.get("domaine") or "") else ""))
    morceaux.append("livraison France : " + p.get("livraison_france", "inconnue"))
    return " ; ".join(morceaux)


def relire(alertes, maxi=4, age_min_minutes=25):
    """Relit les pages des alertes encore à vérifier (les plus anciennes lectures d'abord). Renvoie le nombre relu."""
    now = datetime.now(timezone.utc)
    a_relire = []
    for x in alertes:
        if x.get("statut") not in ("a_verifier", "a_reverifier") or not x.get("lien"):
            continue
        lu = ((x.get("page_offre") or {}).get("lu_le") or "")
        try:
            age = (now - datetime.fromisoformat(lu)).total_seconds() / 60 if lu else 1e9
        except ValueError:
            age = 1e9
        if age >= age_min_minutes:
            a_relire.append((age, x))
    a_relire.sort(key=lambda t: -t[0])
    n = 0
    for _, x in a_relire[:maxi]:
        ancien = x.get("page_offre") or {}
        p = lire_offre(x)
        p["lectures"] = (ancien.get("lectures") or 0) + 1
        p["premiere_lecture"] = ancien.get("premiere_lecture") or ancien.get("lu_le") or p["lu_le"]
        if p.get("expiree") and not ancien.get("expiree"):
            p["expiree_vue_le"] = p["lu_le"]
        x["page_offre"] = p
        n += 1
    return n
