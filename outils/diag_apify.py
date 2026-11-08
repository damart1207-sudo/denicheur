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
