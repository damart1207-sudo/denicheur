"""Lecteurs de PAGES marchands lisibles depuis le cloud (validés par David le 04/11, rythme humain : une lecture par tour).
Source de type "page" dans config/sources.json, champ "lecteur" = nom de la fonction ici.
- nike_promos : nike.com/fr promotions (JSON __NEXT_DATA__ : titre, prix, prix initial, remise %, lien).
- ldlc_promos : ldlc.com/promotions (cartes produit + ancien/nouveau prix).
Les grands sites (Fnac, Darty, Boulanger, Cdiscount, Decathlon, Leroy Merlin…) et les ventes privées (Veepee, Showroomprivé,
Zalando Privé) BLOQUENT les lectures depuis le cloud GitHub (403) ou exigent un compte : voir outils/test_sources2.py.
"""
import hashlib
import html as _html
import json
import re
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _lire(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1500000).decode("utf-8", "replace")


def _annonce(source, titre, prix, lien, prix_initial=None, description="", marchand=None):
    remise = round((1 - prix / prix_initial) * 100) if prix_initial and prix_initial > prix else None
    return {"id": hashlib.sha1(lien.encode()).hexdigest()[:10], "titre": titre[:180], "temperature": (remise or 0) * 8,
            "categorie": source.get("categorie", ""), "marchand": marchand or source.get("marchand") or source["id"], "prix": round(float(prix), 2),
            "devise": "EUR", "lien": lien, "date": "", "source": source["id"], "pays": source.get("pays", "FR"),
            "description": (f"prix initial {prix_initial} €, -{remise} %. " if remise else "") + description}


def nike_promos(source):
    h = _lire(source["url"])
    i = h.find('<script id="__NEXT_DATA__"')
    if i < 0:
        return [], "pas de __NEXT_DATA__"
    j = h.find(">", i) + 1
    k = h.find("</script>", j)
    try:
        data = json.loads(h[j:k])
    except json.JSONDecodeError as e:
        return [], f"JSON illisible: {e}"
    out = []

    def parcourir(o):
        if isinstance(o, dict):
            if "productCode" in o and isinstance(o.get("prices"), dict) and o["prices"].get("currentPrice"):
                p = o["prices"]
                titre = " ".join(x for x in ((o.get("copy") or {}).get("title"), (o.get("copy") or {}).get("subTitle")) if x)
                lien = o.get("pdpUrl") or ""
                if isinstance(lien, dict):
                    lien = lien.get("url") or ""
                if lien and not lien.startswith("http"):
                    lien = "https://www.nike.com" + lien
                if titre and lien:
                    out.append(_annonce(source, titre, p["currentPrice"], lien, p.get("initialPrice"),
                                        f"Nike {o.get('productCode')} ; couleur {((o.get('displayColors') or {}).get('colorDescription') or '')}", "Nike"))
            for v in o.values():
                parcourir(v)
        elif isinstance(o, list):
            for v in o:
                parcourir(v)

    parcourir(data)
    vus = set()
    out = [a for a in out if not (a["id"] in vus or vus.add(a["id"]))]
    return out, None


def ldlc_promos(source):
    h = _lire(source["url"])
    blocs = re.split(r'<li id="pdt-', h)[1:]
    prix_script = {m.group(1): (float(m.group(2) + "." + m.group(3)), float(m.group(4) + "." + m.group(5)))
                   for m in re.finditer(r'data-offer-id="(OF\d+)"\].*?old-price">(\d+)€<sup>(\d+)</sup></div><div class="new-price">(\d+)€<sup>(\d+)</sup>', h, re.S)}
    out = []
    for b in blocs:
        m_t = re.search(r'<h3 class ?="title-3"><a href="([^"]+)">(.*?)</a>', b, re.S)
        m_o = re.search(r'data-offer-id="(OF\d+)"', b)
        if not m_t or not m_o:
            continue
        lien, titre = "https://www.ldlc.com" + m_t.group(1), _html.unescape(re.sub(r"<[^>]+>", "", m_t.group(2))).strip()
        prix = prix_script.get(m_o.group(1))
        if not prix:
            m_p = re.search(r'new-price">(\d+)€<sup>(\d+)</sup>', b) or re.search(r'class="price">\s*(\d+)€<sup>(\d+)</sup>', b)
            if not m_p:
                continue
            prix = (None, float(m_p.group(1) + "." + m_p.group(2)))
        desc = re.search(r'<p class="desc">(.*?)</p>', b, re.S)
        out.append(_annonce(source, titre, prix[1], lien, prix[0], _html.unescape(re.sub(r"<[^>]+>", "", desc.group(1))).strip()[:120] if desc else "", "LDLC"))
    return out, None


LECTEURS = {"nike_promos": nike_promos, "ldlc_promos": ldlc_promos}


def lire(source, timeout=25):
    f = LECTEURS.get(source.get("lecteur"))
    if not f:
        return [], f"lecteur inconnu : {source.get('lecteur')}"
    try:
        return f(source)
    except Exception as e:
        return [], f"{type(e).__name__}: {str(e)[:150]}"
