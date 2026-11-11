"""DÉNICHEUR « STOCK » (11/11/2026) — un des trois dénicheurs testés en parallèle (stock / occasion / grossiste).
Condition lâchée : « sans stock » et « 20 € par pièce ». On cherche des produits NEUFS qui se vendent beaucoup en France,
achetés moins cher sur Amazon Allemagne / Italie / Espagne (même fiche Amazon = identité exacte), à revendre sur une place
de marché où les acheteurs sont déjà là (Amazon, Cdiscount, Fnac). Petite marge par pièce, multipliée par le volume.
  1. base : data/arbitrage.json (écarts calculés en continu par la veille, Keepa) des dernières 36 heures ;
  2. prix étranger + prix français + poids relus à l'instant chez Keepa (1 jeton par produit et par pays) ;
  3. prix de revente = 3 % sous le plus bas entre Amazon.fr aujourd'hui et son prix habituel sur 90 jours ;
  4. marge nette calculée sur CHAQUE place de marché (commission, frais fixes, port, cotisations) ;
  5. preuve par code chez idealo pour les meilleurs (≤ MAX_IDEALO recherches, ≈ 0,01 $ l'une).
Aucun DataForSEO, aucun envoi Telegram.   Lancement : outil = denicheur_stock   Résultat : data/denicheur_stock.json"""
import collections
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import chaine  # noqa: E402
from denicheur.rentabilite import calculer  # noqa: E402

CANAUX = ("amazon", "cdiscount", "fnac")
MARGE_MIN = 5.0          # € net par pièce : petit, mais multiplié par les ventes
VENTES_MIN = 20          # ventes estimées par mois sur Amazon.fr
MAX_PRODUITS = 80
MAX_IDEALO = int(os.environ.get("CHAINE_MAX_IDEALO", "20"))
regles = json.load(open("config/regles.json", encoding="utf-8"))
limite = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M")
base = [x for x in json.load(open("data/arbitrage.json", encoding="utf-8")).get("ecarts", [])
        if (x.get("vu") or "") >= limite and x.get("prix_fr") and x.get("moyenne_90j_fr") and (x.get("ventes_30j_fr") or 0) >= VENTES_MIN]
base.sort(key=lambda x: -(x.get("ventes_30j_fr") or 0))
base = base[:MAX_PRODUITS]
print(f"Écarts entre pays des 36 dernières heures avec ≥ {VENTES_MIN} ventes par mois en France : {len(base)}")


def marges(achat, prix_vente):
    out = {}
    for canal in CANAUX:
        try:
            out[canal] = calculer(prix_vente, canal, achat, regles)["marge_nette"]
        except Exception:
            pass
    return out


fr = chaine.keepa_lot([x["asin"] for x in base], "asin", "FR")
etr = {p: chaine.keepa_lot([x["asin"] for x in base if x["pays_achat"] == p], "asin", p) for p in ("DE", "IT", "ES")}
res, raisons = [], collections.Counter()
for x in base:
    kf, ke = fr.get(x["asin"]) or {}, (etr.get(x["pays_achat"]) or {}).get(x["asin"]) or {}
    if not ke.get("prix_neuf") or not kf.get("prix_neuf"):
        raisons["prix introuvable à la relecture"] += 1
        continue
    poids = ke.get("poids_g") or kf.get("poids_g")
    port = chaine.port_europe(poids)
    if port is None:
        raisons["colis de plus de 15 kg"] += 1
        continue
    achat = round(ke["prix_neuf"] + port, 2)
    ref = min(kf["prix_neuf"], kf.get("moyenne_90j") or kf["prix_neuf"])
    prix_vente = round(ref * chaine.SOUS_LE_MARCHE, 2)
    m = marges(achat, prix_vente)
    if not m or max(m.values()) < MARGE_MIN:
        raisons["marge nette sous 5 € sur toutes les places de marché"] += 1
        continue
    canal = max(m, key=m.get)
    ventes = kf.get("ventes_mois") or kf.get("ventes_estimees_30j") or 0
    if ventes < VENTES_MIN:
        raisons["moins de 20 ventes par mois à la relecture"] += 1
        continue
    res.append({"titre": x["titre"], "ean": chaine.ean13(x["ean"]), "asin": x["asin"], "marque": x.get("marque"), "pays_achat": x["pays_achat"],
                "lien_achat": x["lien_achat"], "lien_fr": x["lien_fr"], "prix_etranger": ke["prix_neuf"], "poids_g": poids, "port": port,
                "achat": achat, "prix_fr": kf["prix_neuf"], "amazon_vend_lui_meme": bool(kf.get("prix_amazon")), "moyenne_90j_fr": kf.get("moyenne_90j"),
                "prix_vente": prix_vente, "marges": m, "meilleur_canal": canal, "marge": m[canal], "ventes_30j_fr": ventes,
                "vendeurs_fr": kf.get("nb_vendeurs_neuf"), "alertes": []})
print(f"Après relecture des prix : {len(res)} produits rentables sur au moins une place de marché ; écartés : {dict(raisons)}")

# preuve par code : le prix le plus bas de France, tous marchands (idealo)
res.sort(key=lambda r: -(r["marge"] * min(r["ventes_30j_fr"], 100)))
nb = 0
for r in res:
    if nb >= MAX_IDEALO:
        r["alertes"].append("non contrôlé chez idealo (limite du passage)")
        continue
    nb += 1
    try:
        i = chaine.idealo_par_code(r["ean"], chaine.requete_google(r["titre"], r.get("marque")))
    except Exception as e:
        i = {"raison": f"idealo en erreur ({type(e).__name__})"}
    r["idealo"] = i
    if i.get("prix_min"):
        if i["prix_min"] < r["prix_vente"]:   # un marchand français est déjà moins cher que notre prix de revente
            r["prix_vente"] = round(i["prix_min"] * chaine.SOUS_LE_MARCHE, 2)
            r["marges"] = marges(r["achat"], r["prix_vente"])
            r["meilleur_canal"] = max(r["marges"], key=r["marges"].get)
            r["marge"] = r["marges"][r["meilleur_canal"]]
            r["alertes"].append(f"idealo : déjà {i['prix_min']} € en France, prix de revente abaissé")
        r["prouve"] = True
    else:
        r["alertes"].append(f"prix français hors Amazon non prouvé par code ({i.get('raison')})")
for r in res:
    if r["amazon_vend_lui_meme"]:
        r["alertes"].append("Amazon vend lui-même ce produit en France : il peut s'aligner sur ton prix")
    if (r["vendeurs_fr"] or 0) <= 1:
        r["alertes"].append("un seul vendeur en France : prix de référence fragile")
    if not r["poids_g"]:
        r["alertes"].append("poids inconnu : port compté 7 €")
    r["gain_mensuel_theorique"] = round(r["marge"] * min(r["ventes_30j_fr"], 100) * 0.1, 2)   # si l'on captait 10 % des ventes
bons = sorted([r for r in res if r["marge"] >= MARGE_MIN], key=lambda r: (-bool(r.get("prouve")), -r["marge"]))
heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M")
ent = collections.OrderedDict([("Écarts entre pays (36 h, ≥ 20 ventes par mois)", len(base)), ("Rentables après relecture des prix", len(res)),
                               ("Recherches idealo par code", nb), ("Prouvés par code", sum(1 for r in bons if r.get("prouve"))),
                               ("Rentables à la fin (≥ 5 € net par pièce)", len(bons))])
json.dump({"maj": heure, "entonnoir": ent, "ecartes": dict(raisons), "produits": bons}, open("data/denicheur_stock.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nENTONNOIR")
for k, n in ent.items():
    print(f"  {n:4d}  {k}")
for r in bons:
    i = r.get("idealo") or {}
    print(f"{'PROUVÉ' if r.get('prouve') else 'à voir':6s} {r['pays_achat']} achat {r['achat']} (port {r['port']}) | FR {r['prix_fr']} (90 j {r['moyenne_90j_fr']}) idealo {i.get('prix_min') or '-'} | vente {r['prix_vente']} | "
          f"marges {r['marges']} | ventes {r['ventes_30j_fr']} vendeurs {r['vendeurs_fr']} | {r['titre'][:55]} | {r['lien_achat']} | {r['alertes']}")
