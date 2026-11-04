"""Garde un échantillon HTML des pages lisibles (pour écrire les lecteurs) : data/echantillons/<nom>.html. outil = echantillon_pages"""
import os, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
URLS = {"nike_promos": "https://www.nike.com/fr/w/promotions-3yaep", "courir_promos": "https://www.courir.com/fr/c/promotions/",
        "rakuten_flash": "https://fr.shopping.rakuten.com/event/ventes-flash", "ldlc_promos": "https://www.ldlc.com/promotions/",
        "amazon_outlet": "https://www.amazon.fr/outlet", "veepee_home": "https://www.veepee.fr/gr/home/default",
        "showroomprive_home": "https://www.showroomprive.com/", "bazarchic": "https://www.bazarchic.com/", "asos_outlet": "https://www.asos.com/fr/outlet/",
        "ikea_offres": "https://www.ikea.com/fr/fr/offers/", "lesnumeriques_rss": "https://www.lesnumeriques.com/bons-plans/rss.xml", "pepper_it": "https://www.pepper.it/rss/hot"}
os.makedirs("data/echantillons", exist_ok=True)
for nom, u in URLS.items():
    try:
        req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
        with urllib.request.urlopen(req, timeout=25) as r:
            h = r.read(900000).decode("utf-8", "replace")
        open(f"data/echantillons/{nom}.html", "w", encoding="utf-8").write(h)
        print("ok", nom, len(h))
    except Exception as e:
        print("--", nom, type(e).__name__, str(e)[:80])
