"""Test GRATUIT de l'API GraphQL de Pepper depuis GitHub (aucune IA appelée).
Pour chaque source pepper : nombre de deals lus en GraphQL, exemples, et comparaison avec le RSS.
Résultat : data/echantillons/test_pepper_graphql.json"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import pepper, collecte

sources = [s for s in json.load(open("config/sources.json", encoding="utf-8"))["sources"] if s["type"] == "pepper" and s.get("actif", True)]
res = {}
for s in sources:
    r = {"url": s["url"]}
    import urllib.parse
    dom = urllib.parse.urlparse(s["url"]).netloc
    for liste in ("hot", "new"):
        try:
            th = pepper.requete(dom, liste)
            r[f"graphql_{liste}"] = {"nb": len(th), "exemple": th[0] if th else None}
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if hasattr(e, "read"):
                try:
                    msg += " | " + e.read()[:400].decode("utf-8", "replace")
                except Exception:
                    pass
            r[f"graphql_{liste}"] = {"erreur": msg[:700]}
        print("  GRAPHQL", s["id"], liste, json.dumps(r[f"graphql_{liste}"], ensure_ascii=False)[:600])
    try:
        items, err = pepper.lire(s)
        r.update({"nb": len(items), "erreur": err, "lecture": items[0]["lecture"] if items else None,
                  "avec_prix": sum(1 for a in items if a.get("prix")), "avec_marchand": sum(1 for a in items if a.get("marchand")),
                  "avec_reference": sum(1 for a in items if a.get("prix_reference")),
                  "exemples": [{k: a.get(k) for k in ("titre", "prix", "prix_reference", "marchand", "temperature", "categorie", "code_promo", "lien")} for a in items[:3]]})
    except Exception as e:
        r["exception"] = f"{type(e).__name__}: {e}"[:300]
    try:
        rss, err2 = collecte.lire_flux(s)
        r["rss_nb"] = len(rss); r["rss_erreur"] = err2
    except Exception as e:
        r["rss_exception"] = str(e)[:200]
    print(s["id"], {k: v for k, v in r.items() if k != "exemples"})
    res[s["id"]] = r
    time.sleep(1)
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_pepper_graphql.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
