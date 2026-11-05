"""GOOGLE SHOPPING par DataForSEO (Merchant API) : tous les marchands qui vendent un produit, avec leurs prix en DONNÉES
(pas de lecture de page). File prioritaire : réponse en moins d'une minute, 0,002 $ par recherche (40 produits).
Sert de second avis indépendant pour la règle « deux sources d'accord »."""
import json
import os
import time
import urllib.request

from . import dataforseo

PAYS = {"FR": (2250, "fr"), "DE": (2276, "de"), "ES": (2724, "es"), "IT": (2380, "it"), "UK": (2826, "en")}
COUT = 0.002


def _get(chemin):
    req = urllib.request.Request("https://api.dataforseo.com/v3/" + chemin,
                                 headers={"Authorization": dataforseo._auth(), "User-Agent": "denicheur/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def chercher(requetes, pays="FR", attente_max=150):
    """requetes : liste de mots-clés (EAN de préférence). Renvoie {requete: [offres]} ; offre = {titre, prix, marchand, lien}."""
    requetes = [q for q in dict.fromkeys(requetes) if q][:100]
    if not requetes or not dataforseo.disponible(COUT * len(requetes)):
        return {}
    loc, langue = PAYS.get(pays, PAYS["FR"])
    taches = dataforseo._poster("merchant/google/products/task_post",
                                [{"keyword": q, "location_code": loc, "language_code": langue, "priority": 2, "tag": q} for q in requetes],
                                COUT * len(requetes))
    ids = {t["id"]: (t.get("data") or {}).get("tag") for t in taches if t.get("id")}
    res, debut = {}, time.monotonic()
    while ids and time.monotonic() - debut < attente_max:
        time.sleep(8)
        for tid in list(ids):
            try:
                d = _get(f"merchant/google/products/task_get/advanced/{tid}")
            except Exception:
                continue
            t = (d.get("tasks") or [{}])[0]
            if t.get("status_code") in (40601, 40602):  # tâche pas encore prête
                continue
            q = ids.pop(tid)
            offres = []
            for r in (t.get("result") or []):
                for it in (r.get("items") or []):
                    p = it.get("price")
                    if isinstance(p, dict):
                        p = p.get("current") or p.get("regular")
                    if isinstance(p, (int, float)) and p > 0:
                        offres.append({"titre": (it.get("title") or "")[:150], "prix": float(p), "marchand": it.get("seller") or it.get("domain"),
                                       "lien": it.get("url") or it.get("shopping_url"), "devise": it.get("currency")})
            res[q] = offres
    return res
