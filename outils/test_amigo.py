"""Test GRATUIT des sources « produits les plus recherchés / vendus » par pays pour Amigo.
Pour chaque source : statut HTTP, blocage (captcha), nombre de produits lus + 5 exemples.
Résultat : data/echantillons/test_amigo.json"""
import json, os, re, time, html, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8", "Accept": "text/html,application/xhtml+xml"}

AMAZON = {"FR": "amazon.fr", "DE": "amazon.de", "IT": "amazon.it", "ES": "amazon.es", "UK": "amazon.co.uk",
          "NL": "amazon.nl", "BE": "amazon.com.be", "SE": "amazon.se", "PL": "amazon.pl", "IE": "amazon.ie",
          "US": "amazon.com", "CA": "amazon.ca", "MX": "amazon.com.mx", "BR": "amazon.com.br", "JP": "amazon.co.jp",
          "IN": "amazon.in", "AU": "amazon.com.au", "SG": "amazon.sg", "AE": "amazon.ae", "SA": "amazon.sa",
          "TR": "amazon.com.tr", "EG": "amazon.eg"}
AUTRES = {
    "JP_rakuten": "https://ranking.rakuten.co.jp/daily/",
    "CN_smzdm": "https://www.smzdm.com/top/",
    "KR_danawa": "https://www.danawa.com/",
    "TW_pchome": "https://24h.pchome.com.tw/",
    "FR_idealo": "https://www.idealo.fr/",
    "FR_fnac_top": "https://www.fnac.com/Les-meilleures-ventes/sh53958/w-4",
    "FR_cdiscount_top": "https://www.cdiscount.com/meilleures-ventes.html",
    "DE_geizhals": "https://geizhals.de/?o=8",
    "US_bestbuy": "https://www.bestbuy.com/site/misc/best-sellers/pcmcat1515608839924.c",
    "FR_leboncoin": "https://www.leboncoin.fr/",
}

def lire(u):
    req = urllib.request.Request(u, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, r.read().decode("utf-8", errors="replace")

def titres_amazon(h):
    t = re.findall(r'p13n-sc-css-line-clamp-\d[^>]*>([^<]{8,200})<', h)
    t += re.findall(r'p13n-sc-truncate[^>]*>\s*([^<]{8,200})<', h)
    t += re.findall(r'<img alt="([^"]{12,200})" src="https://images-[^"]+"[^>]*class="[^"]*p13n', h)
    vus, out = set(), []
    for x in t:
        x = html.unescape(x.strip())
        if x not in vus:
            vus.add(x); out.append(x)
    return out

res = {}
for pays, dom in AMAZON.items():
    u = f"https://www.{dom}/gp/bestsellers/electronics/"
    try:
        st, h = lire(u)
        bloque = bool(re.search(r"captcha|robot check|Saisissez les caractères|api-services-support", h, re.I))
        t = titres_amazon(h)
        res[f"amazon_{pays}"] = {"statut": st, "bloque": bloque, "taille": len(h), "nb": len(t), "exemples": t[:5]}
    except Exception as e:
        res[f"amazon_{pays}"] = {"erreur": str(e)[:120]}
    time.sleep(2)

for nom, u in AUTRES.items():
    try:
        st, h = lire(u)
        bloque = bool(re.search(r"captcha|cf-chl|challenge-platform|access denied|datadome", h, re.I))
        res[nom] = {"statut": st, "bloque": bloque, "taille": len(h), "titre_page": (re.findall(r"<title>([^<]*)", h) or [""])[0][:100]}
    except Exception as e:
        res[nom] = {"erreur": str(e)[:120]}
    time.sleep(2)

os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_amigo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in res.items():
    print(k, v.get("nb", ""), v.get("statut", v.get("erreur", "")), "BLOQUÉ" if v.get("bloque") else "")
