"""CHAÎNE EAN, troisième entrée : ÉCARTS ENTRE PAYS (10/11/2026). Le même produit Amazon (même ASIN, donc identité
exacte) moins cher en Allemagne, Italie ou Espagne qu'en France. Point de départ : data/arbitrage.json (calculé en
continu par la veille avec Keepa). Ici on REVÉRIFIE tout avant de parler d'affaire :
  1. prix étranger et prix français relus chez Keepa à l'instant (1 jeton par produit et par pays) ;
  2. référence prudente = le plus bas entre le prix Amazon.fr du moment et son prix habituel sur 90 jours ;
  3. preuve par code : prix neuf le plus bas de France chez idealo pour ce code EAN (≈ 0,01 $ par recherche).
Aucun envoi Telegram. Coût : aucun appel DataForSEO ; idealo ≤ MAX_IDEALO recherches.
Lancement : outil = chaine_pays      Résultat : data/chaine_pays.json"""
import collections
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import chaine  # noqa: E402

PORT = 7.0
MAX_PRODUITS = 60
MAX_IDEALO = int(os.environ.get("CHAINE_MAX_IDEALO", "22"))
regles = json.load(open("config/regles.json", encoding="utf-8"))
jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
ecarts = [x for x in json.load(open("data/arbitrage.json", encoding="utf-8")).get("ecarts", [])
          if (x.get("vu") or "")[:10] == jour and x.get("prix_fr") and x.get("moyenne_90j_fr") and chaine.ean13(x.get("ean"))]


def refs_amazon(prix_fr, moy90):
    r = []
    if prix_fr:
        r.append({"marchand": "Amazon.fr aujourd'hui", "total": prix_fr, "gros": True})
    if moy90:
        r.append({"marchand": "Amazon.fr, prix habituel sur 90 jours", "total": moy90, "gros": True})
    return r


# tri gratuit sur les données de la veille
pre = []
for x in ecarts:
    v = chaine.verdict(x["cout_rendu"], refs_amazon(x["prix_fr"], x["moyenne_90j_fr"]), True, regles, x.get("ventes_30j_fr"))
    if v["feu"] != "rouge":
        pre.append((v.get("marge_nette") or 0, x))
pre = [x for _, x in sorted(pre, key=lambda t: -t[0])][:MAX_PRODUITS]
print(f"Écarts entre pays du jour : {len(ecarts)} ; passent le tri gratuit : {len(pre)}")

# 1. prix relus à l'instant (Keepa)
fr = chaine.keepa_lot([x["asin"] for x in pre], "asin", "FR")
etr = {}
for pays in ("DE", "IT", "ES"):
    asins = [x["asin"] for x in pre if x["pays_achat"] == pays]
    if asins:
        etr[pays] = chaine.keepa_lot(asins, "asin", pays)

affaires, a_prouver = [], []
for x in pre:
    kf, ke = fr.get(x["asin"]) or {}, (etr.get(x["pays_achat"]) or {}).get(x["asin"]) or {}
    c = {"denicheur": "Pays", "titre": x["titre"], "ean": chaine.ean13(x["ean"]), "asin": x["asin"], "pays_achat": x["pays_achat"],
         "lien_achat": x["lien_achat"], "lien_fr": x["lien_fr"], "marque": x.get("marque"),
         "prix_etranger": ke.get("prix_neuf"), "prix_etranger_amazon": ke.get("prix_amazon"), "prix_fr": kf.get("prix_neuf"),
         "moyenne_90j_fr": kf.get("moyenne_90j"), "vendeurs_fr": kf.get("nb_vendeurs_neuf"),
         "ventes_30j_fr": kf.get("ventes_mois") or kf.get("ventes_estimees_30j")}
    if not c["prix_etranger"] or not c["prix_fr"]:
        c["verdict"] = {"feu": "rouge", "raison": "prix introuvable à la relecture (plus d'offre neuve ?)"}
    else:
        c["achat"] = round(c["prix_etranger"] + PORT, 2)
        c["verdict"] = chaine.verdict(c["achat"], refs_amazon(c["prix_fr"], c["moyenne_90j_fr"]), True, regles, c["ventes_30j_fr"])
        if c["verdict"]["feu"] != "rouge":
            a_prouver.append(c)
    affaires.append(c)
print(f"Après relecture des prix : {len(a_prouver)} écarts tiennent encore")

# 2. preuve par code chez idealo (France, tous marchands)
a_prouver.sort(key=lambda c: -(c["verdict"].get("marge_nette") or 0))
nb = 0
for c in a_prouver:
    v = c["verdict"]
    v["manque"] = [m for m in v.get("manque", []) if "pas d'accord" not in m]   # deux prix du même Amazon : pas un désaccord entre marchands
    if nb >= MAX_IDEALO:
        v["manque"].append("non recherché chez idealo (limite du passage)")
        v["feu"] = "orange"
        continue
    nb += 1
    try:
        i = chaine.idealo_par_code(c["ean"], chaine.requete_google(c["titre"], c.get("marque")))
    except Exception as e:
        i = {"raison": f"idealo en erreur ({type(e).__name__})"}
    c["idealo"] = i
    if not i.get("prix_min"):
        v["manque"].append(f"prix français hors Amazon non prouvé par code : {i.get('raison')}")
        v["feu"] = "orange"
        continue
    refs = [{"marchand": f"idealo, moins cher de France pour ce code ({i.get('nb_offres') or '?'} offres)", "total": i["prix_min"], "gros": True, "lien": i.get("lien")}]
    refs += refs_amazon(c["prix_fr"], c["moyenne_90j_fr"])
    c["verdict"] = chaine.verdict(c["achat"], refs, True, regles, c["ventes_30j_fr"], preuve_code=True)
    c["refs"] = refs
for c in affaires:
    if c["verdict"]["feu"] != "rouge":
        c["verdict"].setdefault("a_completer", []).append(f"livraison Amazon {c['pays_achat']} vers la France et port réel : à vérifier au panier (7 € comptés)")

ordre = {"vert": 0, "orange": 1, "rouge": 2}
affaires.sort(key=lambda c: (ordre[c["verdict"]["feu"]], -(c["verdict"].get("marge_nette") or -999)))
ent = collections.OrderedDict([
    ("Écarts entre pays du jour (base de la veille)", len(ecarts)),
    ("Passent le tri gratuit", len(pre)),
    ("Tiennent après relecture des prix à l'instant", len(a_prouver)),
    ("Recherches idealo par code", nb),
    ("Fiche idealo au bon code", sum(1 for c in a_prouver if (c.get("idealo") or {}).get("prix_min"))),
    ("Verts", sum(1 for c in affaires if c["verdict"]["feu"] == "vert")),
    ("Oranges", sum(1 for c in affaires if c["verdict"]["feu"] == "orange")),
])
heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M")
json.dump({"maj": heure, "entonnoir": ent, "affaires": affaires}, open("data/chaine_pays.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nENTONNOIR")
for k, n in ent.items():
    print(f"  {n:4d}  {k}")
for c in affaires:
    v = c["verdict"]
    if v["feu"] == "rouge" and not c.get("idealo"):
        continue
    i = c.get("idealo") or {}
    print(f"{v['feu'].upper():6s} {c['pays_achat']} achat {c.get('achat')} | FR {c.get('prix_fr')} (90 j {c.get('moyenne_90j_fr')}) | idealo {i.get('prix_min') or i.get('raison')} | "
          f"vente {v.get('prix_vente')} marge {v.get('marge_nette')} | ventes {c.get('ventes_30j_fr')} vendeurs {c.get('vendeurs_fr')} | {c['titre'][:60]} | {c['lien_achat']} | {v.get('manque') or v.get('raison')}")
