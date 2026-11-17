"""Diagnostic réel : le robot Leboncoin ne renvoie plus aucune annonce depuis le 06/11 (journal). Pourquoi, et quel remplaçant ?
Pour le robot actuel et quelques candidats : schéma d'entrée (gratuit), puis UN essai plafonné à 0,02 $ chacun sur un produit
réel du jour, avec l'état de l'exécution et la fin de son journal. Coût total ≤ 0,02 $ × nombre d'essais (5 au plus = 0,10 $).
outil = diag_leboncoin"""
import json, os, sys, urllib.parse, urllib.request
Q = os.environ.get("Q", "motorola edge 50 neo")
TOK = os.environ["APIFY_TOKEN"].strip()
URL = "https://www.leboncoin.fr/recherche?text=" + urllib.parse.quote(Q)


def api(chemin, data=None, brut=False):
    req = urllib.request.Request("https://api.apify.com/v2/" + chemin, data=json.dumps(data).encode() if data is not None else None,
                                 method="POST" if data is not None else "GET",
                                 headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=200) as r:
            c = r.read()
            return c.decode("utf-8", "replace") if brut else json.loads(c or b"{}")
    except urllib.error.HTTPError as e:
        return {"erreur": f"HTTP {e.code}: {e.read()[:400].decode('utf-8', 'replace')}"}
    except Exception as e:
        return {"erreur": f"{type(e).__name__}: {e}"}


ESSAIS = [
    ("fatihtahta~leboncoin-fr-scraper", {"startUrls": [URL], "limit": 15}),
    ("fatihtahta~leboncoin-fr-scraper", {"queries": [Q], "limit": 15}),
    ("memo23~leboncoin-scraper", {"startUrls": [{"url": URL}], "maxItems": 15}),
    ("scrapifier~leboncoin-scraper", {"startUrls": [{"url": URL}], "maxItems": 15}),
    ("silentflow~leboncoin-scraper-ppr", {"startUrls": [{"url": URL}], "maxItems": 15}),
]
vus = set()
for acteur, entree in ESSAIS:
    print("\n=====", acteur)
    if acteur not in vus:
        vus.add(acteur)
        b = api(f"acts/{acteur}/builds/default")
        sch = ((b.get("data") or {}).get("actorDefinition") or {}).get("input") or (b.get("data") or {}).get("inputSchema")
        if isinstance(sch, str):
            try:
                sch = json.loads(sch)
            except ValueError:
                sch = None
        if isinstance(sch, dict):
            for k, v in (sch.get("properties") or {}).items():
                print("  champ", k, "|", v.get("type"), "|", str(v.get("default"))[:60], "|", (v.get("description") or v.get("title") or "")[:110].replace("\n", " "))
            print("  obligatoires :", sch.get("required"))
        else:
            print("  schéma illisible :", str(b)[:300])
    print("  entrée :", json.dumps(entree, ensure_ascii=False)[:200])
    r = api(f"acts/{acteur}/runs?" + urllib.parse.urlencode({"waitForFinish": 120, "maxTotalChargeUsd": 0.02, "maxItems": 15}), entree)
    d = r.get("data") or {}
    if not d:
        print("  lancement :", str(r)[:400])
        continue
    print("  état :", d.get("status"), "|", d.get("statusMessage"), "| coût", (d.get("usageTotalUsd")), "| facturé", d.get("chargedEventCounts"))
    items = api(f"datasets/{d.get('defaultDatasetId')}/items?limit=15&clean=true")
    if isinstance(items, list):
        print("  annonces :", len(items))
        for it in items[:6]:
            print("   -", json.dumps({k: it.get(k) for k in ("title", "subject", "price", "pricing", "url") if k in it}, ensure_ascii=False)[:260])
        if items:
            print("  champs :", sorted(items[0])[:40])
    else:
        print("  annonces :", str(items)[:300])
    journal = api(f"actor-runs/{d.get('id')}/log", brut=True)
    print("  fin du journal :", (journal if isinstance(journal, str) else str(journal))[-900:].replace("\n", "\n    "))
