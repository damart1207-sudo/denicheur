"""Test : un vrai navigateur (Playwright) depuis GitHub peut-il lire idealo / ledenicheur / Leboncoin ?"""
import json
import re
from playwright.sync_api import sync_playwright

URLS = {
    "idealo": "https://www.idealo.fr/prechcat.html?q=garmin%20forerunner%20165",
    "ledenicheur": "https://ledenicheur.fr/search?search=garmin%20forerunner%20165",
    "leboncoin": "https://www.leboncoin.fr/recherche?text=garmin%20forerunner%20165",
    "achatmoinscher_promos": "https://www.achatmoinscher.com/comparateur-de-prix-Smartphone/?tri=5&etat=2",
}
res = {}
with sync_playwright() as p:
    nav = p.chromium.launch()
    ctx = nav.new_context(locale="fr-FR", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")
    for nom, u in URLS.items():
        page = ctx.new_page()
        try:
            r = page.goto(u, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            txt = page.inner_text("body")[:20000]
            res[nom] = {"code": r.status if r else None, "titre": page.title()[:100], "taille": len(txt),
                        "prix_vus": re.findall(r"\d{2,4}[,.]\d{2}\s?€", txt)[:6], "extrait": txt[:200]}
        except Exception as e:
            res[nom] = {"erreur": f"{type(e).__name__}: {str(e)[:150]}"}
        print(nom, res[nom])
        page.close()
    nav.close()
with open("data/test_playwright.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
