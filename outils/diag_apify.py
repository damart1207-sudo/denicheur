"""Diagnostic : pourquoi le robot idealo ne répond plus (08/11/2026)."""
import json, os, sys, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import apify
print("jeton présent :", bool(os.environ.get("APIFY_TOKEN", "").strip()))
try:
    req = urllib.request.Request("https://api.apify.com/v2/users/me/limits",
                                 headers={"Authorization": f"Bearer {os.environ['APIFY_TOKEN'].strip()}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())["data"]
        print("limits OK :", json.dumps({"current": d.get("current"), "limits": d.get("limits")})[:600])
except urllib.error.HTTPError as e:
    print("limits HTTP", e.code, e.read()[:300])
except Exception as e:
    print("limits erreur", type(e).__name__, e)
apify.CONTEXTE["denicheur"] = "P"
print("dépense réelle :", apify.depense_reelle(), "| du jour P :", apify.depense_du_jour("P"), "| disponible :", apify.disponible())
print("test idealo :", apify.prix_idealo("Nespresso Vertuo Next"))
from denicheur import budget
try:
    st = budget.stockage()
    def voir(e):
        s = e.get("services", {}).get("apify", {})
        print("registre apify :", {k: v for k, v in s.items() if k != "reserves"}, "réserves en cours :", len(s.get("reserves", {})))
    st.modifier(voir)
except Exception as e:
    print("registre erreur :", type(e).__name__, e)
items = apify.lancer("idealo", {"searchQuery": "Nespresso Vertuo Next", "country": "FR", "maxItems": 3, "fetchOffers": False}, maxi=3)
print("lancer idealo :", None if items is None else len(items))
for i in (items or [])[:3]:
    print("  ", json.dumps({k: i.get(k) for k in ("title", "price", "url", "offerCount", "gtin")}, ensure_ascii=False)[:300] if isinstance(i, dict) else i)
