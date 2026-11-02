"""Notre base de données à nous : TOUT ce que les dénicheurs voient est gardé, jour après jour.

data/base/prix/AAAA-MM-JJ.jsonl.gz   une ligne par prix observé (produit, pays, site, prix, lien, source, dénicheur)
data/base/demande/AAAA-MM-JJ.json    ce qu'Amigo a trouvé comme « produits les plus recherchés » par pays
data/base/produits.json              index : pour chaque produit, prix mini/maxi/moyen vus, nb d'observations, pays, dernière vue

But : à terme, connaître le prix habituel de chaque produit sans logiciel payant."""
import datetime as dt, gzip, json, os, re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(RACINE, "data", "base")
_tampon = []


def _jour():
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


def cle(nom):
    """Clé produit stable : minuscules, sans accents ni ponctuation."""
    import unicodedata
    n = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def noter_prix(produit, prix, pays="", site="", lien="", devise="EUR", source="", denicheur="", etat="neuf"):
    """Garde une observation de prix (en mémoire, écrite par sauver())."""
    try:
        prix = round(float(prix), 2)
    except (TypeError, ValueError):
        return
    if not produit or prix <= 0:
        return
    _tampon.append({"t": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M"), "produit": produit, "cle": cle(produit),
                    "prix": prix, "devise": devise, "pays": pays, "site": site, "lien": lien,
                    "source": source, "den": denicheur, "etat": etat})


def noter_demande(liste, origine="amigo"):
    """liste = [{"pays":..., "rang":..., "produit":..., "source":..., "categorie":...}]"""
    os.makedirs(os.path.join(BASE, "demande"), exist_ok=True)
    f = os.path.join(BASE, "demande", _jour() + ".json")
    old = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else []
    old += [dict(x, origine=origine, t=dt.datetime.utcnow().strftime("%H:%M")) for x in liste]
    json.dump(old, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def sauver():
    """Écrit le tampon dans le fichier du jour (gzip) et met à jour l'index produits."""
    global _tampon
    if not _tampon:
        return 0
    os.makedirs(os.path.join(BASE, "prix"), exist_ok=True)
    f = os.path.join(BASE, "prix", _jour() + ".jsonl.gz")
    with gzip.open(f, "at", encoding="utf-8") as g:
        for o in _tampon:
            g.write(json.dumps(o, ensure_ascii=False) + "\n")
    fi = os.path.join(BASE, "produits.json")
    idx = json.load(open(fi, encoding="utf-8")) if os.path.exists(fi) else {}
    for o in _tampon:
        if o["devise"] != "EUR" or o["etat"] != "neuf":
            continue
        p = idx.setdefault(o["cle"], {"nom": o["produit"], "n": 0, "somme": 0.0, "min": o["prix"], "max": o["prix"], "pays": []})
        p["n"] += 1
        p["somme"] = round(p["somme"] + o["prix"], 2)
        p["min"] = min(p["min"], o["prix"])
        p["max"] = max(p["max"], o["prix"])
        if o["pays"] and o["pays"] not in p["pays"]:
            p["pays"].append(o["pays"])
        p["vu"] = o["t"]
    json.dump(idx, open(fi, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    n = len(_tampon)
    _tampon = []
    return n


def prix_habituel(produit, jours=60):
    """Prix « normal » d'un produit d'après NOTRE base : médiane des prix neufs en euros vus sur la période."""
    k = cle(produit)
    vus = []
    d = os.path.join(BASE, "prix")
    if not os.path.isdir(d):
        return None
    limite = (dt.datetime.utcnow() - dt.timedelta(days=jours)).strftime("%Y-%m-%d")
    for nom in sorted(os.listdir(d)):
        if nom[:10] < limite:
            continue
        with gzip.open(os.path.join(d, nom), "rt", encoding="utf-8") as g:
            for ligne in g:
                o = json.loads(ligne)
                if o.get("cle") == k and o.get("devise") == "EUR" and o.get("etat") == "neuf":
                    vus.append(o["prix"])
    if len(vus) < 3:
        return None
    vus.sort()
    return {"mediane": vus[len(vus) // 2], "min": vus[0], "max": vus[-1], "n": len(vus)}
