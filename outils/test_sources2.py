"""Test (gratuit) des sources supplémentaires validées par David le 04/11 : ventes privées, déstockage des grands sites,
comparateurs, flux de bons plans en plus. Pour chacune : lisible depuis GitHub Actions ? taille ? prix trouvés ? JSON ?
-> data/test_sources2.json      outil = test_sources2"""
import json
import re
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
URLS = {
    # ventes privées
    "showroomprive_ventes": "https://www.showroomprive.com/ventes-en-cours.aspx",
    "showroomprive_home": "https://www.showroomprive.com/",
    "veepee_home": "https://www.veepee.fr/gr/home/default",
    "veepee_api": "https://www.veepee.fr/api/homepage",
    "zalando_prive": "https://www.zalando-prive.fr/",
    "privalia_es": "https://www.privalia.com/public",
    "bazarchic": "https://www.bazarchic.com/",
    "vente_unique_promos": "https://www.vente-unique.com/promotions",
    # déstockage / bons plans des grands sites
    "cdiscount_bonsplans": "https://www.cdiscount.com/bons-plans",
    "cdiscount_fin_serie": "https://www.cdiscount.com/vente-flash",
    "fnac_bonsplans": "https://www.fnac.com/Bons-plans",
    "fnac_destockage": "https://www.fnac.com/destockage",
    "boulanger_bonsplans": "https://www.boulanger.com/evt/bons-plans",
    "boulanger_occasions": "https://www.boulanger.com/c/occasions",
    "darty_bonsplans": "https://www.darty.com/nav/extra/bons_plans",
    "darty_occasion": "https://www.darty.com/nav/extra/produits_occasion",
    "decathlon_seconde_vie": "https://www.decathlon.fr/seconde-vie",
    "decathlon_promos": "https://www.decathlon.fr/all-sports/promotions",
    "rakuten_ventes_flash": "https://fr.shopping.rakuten.com/event/ventes-flash",
    "manomano_bonsplans": "https://www.manomano.fr/bons-plans",
    "ldlc_promos": "https://www.ldlc.com/promotions/",
    "ldlc_rss": "https://www.ldlc.com/rss/promotions.xml",
    "amazon_outlet": "https://www.amazon.fr/outlet",
    "leclerc_promos": "https://www.e.leclerc/cat/promotions",
    "lidl_online": "https://www.lidl.fr/c/offres-en-ligne/s10008094",
    "action_offres": "https://www.action.com/fr-fr/offres/",
    "but_promos": "https://www.but.fr/promos/",
    "conforama_promos": "https://www.conforama.fr/promos",
    "ikea_derniere_chance": "https://www.ikea.com/fr/fr/offers/",
    "castorama_promos": "https://www.castorama.fr/promotions/",
    "leroymerlin_promos": "https://www.leroymerlin.fr/promotions/",
    "intersport_promos": "https://www.intersport.fr/promotions/",
    "courir_promos": "https://www.courir.com/fr/c/promotions/",
    "zalando_outlet": "https://www.zalando.fr/outlet/",
    "asos_outlet": "https://www.asos.com/fr/outlet/",
    "nike_promos": "https://www.nike.com/fr/w/promotions-3yaep",
    "adidas_outlet": "https://www.adidas.fr/outlet",
    "backmarket_bonsplans": "https://www.backmarket.fr/fr-fr/l/bons-plans/0d7f5f5d-1d84-4c1e-8d6a-cfa6f2f2b7b2",
    # comparateurs / prix
    "ledenicheur_api": "https://ledenicheur.fr/api/search?q=airpods",
    "ledenicheur_search": "https://ledenicheur.fr/search?search=airpods",
    "geizhals_deals": "https://geizhals.de/?cat=deals",
    "idealo_de": "https://www.idealo.de/preisvergleich/MainSearchProductCategory.html?q=airpods",
    "pricerunner_uk": "https://www.pricerunner.com/search?q=airpods",
    "compare_kelkoo": "https://www.kelkoo.fr/recherche?q=airpods",
    "google_shopping_fr": "https://www.google.fr/search?tbm=shop&q=airpods+pro",
    # flux de bons plans en plus
    "dealabs_ventes_privees_rss": "https://www.dealabs.com/groupe/ventes-privees/rss",
    "dealabs_groupe_mode_rss": "https://www.dealabs.com/groupe/mode-accessoires/rss",
    "pepper_it_hot": "https://www.pepper.it/rss/hot",
    "mydealz_neu": "https://www.mydealz.de/rss/neu",
    "tomsguide_bonsplans": "https://www.tomsguide.fr/bons-plans/feed/",
    "pressecitron_bonsplans": "https://www.presse-citron.net/bons-plans/feed/",
    "phonandroid_bonsplans": "https://www.phonandroid.com/bons-plans/feed",
    "futura_bonsplans": "https://www.futura-sciences.com/rss/bons-plans.xml",
    "lesbonsplans_rss": "https://www.lesbonsplans.fr/feed/",
    "bonsplans_lesnumeriques_rss": "https://www.lesnumeriques.com/bons-plans/rss.xml",
    "reddit_frugalfrance": "https://www.reddit.com/r/vosfinances/.rss",
    "kimovil_fr_baisses": "https://www.kimovil.com/fr/ou-acheter-pas-cher",
}


def essayer(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, r.read(600000).decode("utf-8", "replace"), r.headers.get("Content-Type", "")


res = {}
for nom, u in URLS.items():
    try:
        code, h, ct = essayer(u)
        prix = re.findall(r"(\d{1,4}[,.]\d{2})\s?(?:€|&euro;|&nbsp;€)", h)
        bloque = bool(re.search(r"captcha|datadome|access denied|cloudflare|robot|blocked|verify you are human|pardon our interruption", h, re.I)) and len(h) < 60000
        res[nom] = {"ok": code == 200 and not bloque, "code": code, "taille": len(h), "type": ct[:40], "prix": len(prix),
                    "items_rss": h.count("<item") + h.count("<entry"), "bloque": bloque, "json": h.lstrip().startswith(("{", "["))}
    except Exception as e:
        res[nom] = {"ok": False, "erreur": f"{type(e).__name__}: {str(e)[:100]}"}
    print(("✅" if res[nom]["ok"] else "❌"), nom, {k: v for k, v in res[nom].items() if k != "ok"})
json.dump(res, open("data/test_sources2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
