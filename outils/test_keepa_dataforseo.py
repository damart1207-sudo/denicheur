"""Test des nouveaux outils payants (coût réel : ~0,15 $) : Keepa (EAN connus) et DataForSEO (volumes + tendances).
Résultat : data/echantillons/test_keepa_dataforseo.json"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import keepa, dataforseo

res = {"keepa": {}, "dataforseo": {}}
print("KEEPA clé présente :", bool(keepa.cle()))
for nom, ean in [("AMD Ryzen 7 7800X3D", "730143314930"), ("Garmin Forerunner 265 noir", "0753759302146"), ("Casio G-Shock GA-2100-1A1ER", "4549526241642")]:
    try:
        f = keepa.fiche(ean=ean, pays="FR")
    except Exception as e:
        f = {"exception": f"{type(e).__name__}: {e}"[:300]}
    res["keepa"][nom] = f
    print("KEEPA", nom, json.dumps(f, ensure_ascii=False)[:400])
print("DATAFORSEO identifiants présents :", dataforseo._auth() is not None)
try:
    v = dataforseo.volumes(["garmin forerunner 265", "ryzen 7 7800x3d", "casio ga-2100", "dyson v12", "lego technic"], "FR")
except Exception as e:
    v = {"exception": f"{type(e).__name__}: {e}"[:300]}
res["dataforseo"]["volumes"] = v
print("VOLUMES", json.dumps(v, ensure_ascii=False)[:600])
try:
    t = dataforseo.tendances(["garmin forerunner 265", "dyson v12"], "FR")
except Exception as e:
    t = {"exception": f"{type(e).__name__}: {e}"[:300]}
res["dataforseo"]["tendances"] = {k: {kk: vv for kk, vv in val.items() if kk != "serie"} for k, val in t.items()} if isinstance(t, dict) and "exception" not in t else t
print("TENDANCES", json.dumps(res["dataforseo"]["tendances"], ensure_ascii=False)[:600])
try:
    h = dataforseo.decalage_hype("cmf watch pro 2")
except Exception as e:
    h = {"exception": f"{type(e).__name__}: {e}"[:300]}
res["dataforseo"]["decalage_hype"] = h
print("HYPE", json.dumps(h, ensure_ascii=False)[:500])
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_keepa_dataforseo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
