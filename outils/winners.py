"""PRODUITS GAGNANTS (méthode de David, 05/11) :
 1. Amazon.fr (n° 1 du e-commerce en France) : produits dont les VENTES MONTENT sur les 15 derniers jours
    (historique réel du classement des ventes Amazon, lu par Keepa : classement il y a 15 jours vs aujourd'hui),
    avec un vrai volume de ventes (« X achetés le mois dernier » d'Amazon) — pas les n° 1 installés ;
 2. recherches Google (volume mensuel + courbe Google Trends 30 jours) ;
 3. concurrence (nombre d'offres neuves sur Amazon + nombre de vendeurs sur Google Shopping) ;
 4. chasse : le même produit (contrôle « même produit ») moins cher chez un vendeur pro français.
Aucun chiffre inventé : une donnée absente est écrite « inconnu ».
Coût : Keepa (abonnement) ≈ 300 jetons ; DataForSEO ≈ 0,30 $.   Lancement : outil = winners  -> data/winners.html + Telegram"""
import html as H
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import dataforseo, meme_produit, moisson, shopping, telegram  # noqa: E402

CATS = [(590748031, "Bricolage"), (322086011, "Jeux et Jouets"), (13921051, "High-Tech"), (3557027031, "Jardin"),
        (206617031, "Bébé"), (57004031, "Cuisine et Maison"), (1571265031, "Auto et Moto"), (325614031, "Sports et Loisirs"),
        (213080031, "Luminaires"), (530490, "Jeux vidéo"), (340858031, "Informatique"), (197858031, "Beauté"),
        (1571268031, "Animalerie"), (340861031, "Instruments")]
CONSOMMABLE = re.compile(r"croquette|p[âa]t[ée]e|litière|recharge|cartouche|toner|couche|lessive|capsule|dosette|filtre|"
                         r"shampo|cr[èe]me|s[ée]rum|gel douche|dentifrice|savon|lingette|piles?\b|ampoule|sachet|aliment|"
                         r"compl[ée]ment|vitamine|gélule|recharge|encre|papier|stylo|cahier|calendrier de l.avent", re.I)
JOUR = 24 * 60
SEUIL = 1.25   # ventes au moins 25 % plus fortes qu'il y a 15 jours
OCC = re.compile(r"leboncoin|ebay|vinted|back ?market|rakuten|rebuy|occasion|reconditionn|amazon|idealo|ledenicheur|achatmoinscher|kelkoo", re.I)


def jetons(min_requis):
    """Attend (15 min max) d'avoir assez de jetons Keepa : 20 jetons/minute."""
    debut = time.time()
    while moisson.jetons_restants() < min_requis and time.time() - debut < 900:
        time.sleep(60)
        moisson._jetons["restants"] = None
    return moisson.jetons_restants()


def km_maintenant():
    return int(time.time() / 60) - 21564000


def valeur_a(serie, km):
    """Valeur d'une série Keepa [t, v, t, v…] au temps km (dernière valeur connue)."""
    v = None
    for i in range(0, len(serie) - 1, 2):
        if serie[i] > km:
            break
        if serie[i + 1] is not None and serie[i + 1] > 0:
            v = serie[i + 1]
    return v


def mediane_jours(serie, j_debut, j_fin):
    now = km_maintenant()
    vals = [valeur_a(serie, now - j * JOUR) for j in range(j_debut, j_fin + 1)]
    vals = [v for v in vals if v]
    return statistics.median(vals) if vals else None


def candidats():
    asins, cat_de = [], {}
    for cid, nom in CATS:
        if jetons(60) < 60:
            print("jetons Keepa insuffisants, arrêt de la recherche"); break
        base = {"rootCategory": [cid], "current_NEW_gte": 1500, "current_NEW_lte": 25000, "productType": 0,
                "monthlySold_gte": 100, "perPage": 50, "page": 0}
        essais = [{**base, "deltaPercent30_SALES_lte": -20, "sort": [["monthlySold", "desc"]]},
                  {**base, "salesRankDrops30_gte": 30, "sort": [["monthlySold", "desc"]]}]
        for sel in essais:
            try:
                d = moisson._appel("query", {"domain": 4, "selection": json.dumps(sel)})
                lst = d.get("asinList") or []
                print(f"{nom}: {len(lst)} produits (filtre {'hausse 30 j' if 'deltaPercent30_SALES_lte' in sel else 'ventes 30 j'})")
                if lst:
                    for a in lst[:25]:
                        if a not in cat_de:
                            asins.append(a); cat_de[a] = nom
                    break
            except Exception as e:
                print(f"{nom}: erreur {str(e)[:150]}")
    return asins, cat_de


def fiches(asins):
    out = []
    for i in range(0, len(asins), 50):
        lot = asins[i:i + 50]
        if jetons(len(lot) + 10) < len(lot) + 10:
            print("jetons insuffisants pour les fiches"); break
        d = moisson._appel("product", {"domain": 4, "asin": ",".join(lot), "stats": 30, "history": 1, "days": 40})
        out += [p for p in (d.get("products") or []) if isinstance(p, dict)]
    return out


def analyser(p, cat):
    csv = p.get("csv") or []
    rang = csv[3] if len(csv) > 3 and csv[3] else []
    r_now, r_15 = mediane_jours(rang, 0, 2), mediane_jours(rang, 14, 16)
    ms = p.get("monthlySoldHistory") or []
    v_now = p.get("monthlySold") if isinstance(p.get("monthlySold"), int) and p.get("monthlySold") > 0 else None
    v_15 = valeur_a(ms, km_maintenant() - 15 * JOUR) if ms else None
    st = p.get("stats") or {}
    cur, a30 = st.get("current") or [], st.get("avg30") or []

    def c(s, i):
        return round(s[i] / 100, 2) if len(s) > i and isinstance(s[i], int) and s[i] > 0 else None
    prix = min([x for x in (c(cur, 0), c(cur, 1)) if x], default=None)
    offres = cur[11] if len(cur) > 11 and isinstance(cur[11], int) and cur[11] >= 0 else None
    return {"asin": p.get("asin"), "titre": (p.get("title") or "")[:300], "marque": p.get("brand"), "cat": cat,
            "ean": (p.get("eanList") or [None])[0], "prix_amazon": prix, "prix_moy30": min([x for x in (c(a30, 0), c(a30, 1)) if x], default=None),
            "rang_now": r_now, "rang_15j": r_15, "hausse": round(r_15 / r_now, 2) if r_now and r_15 else None,
            "vendus_mois": v_now, "vendus_mois_15j": v_15, "offres_neuves": offres,
            "lien": f"https://www.amazon.fr/dp/{p.get('asin')}"}


def requete(t):
    """Nom court pour Google : marque + modèle (on coupe à la première virgule, tiret entouré d'espaces, parenthèse…)."""
    t = re.split(r"\s[-–|]\s|,|\(|\[", t)[0].replace(":", " ")
    return " ".join(t.split()[:6]).lower()


def main():
    asins, cat_de = candidats()
    print("candidats", len(asins))
    prods = [analyser(p, cat_de.get(p.get("asin"))) for p in fiches(asins)]
    montent = [x for x in prods if x["hausse"] and x["hausse"] >= SEUIL and x["vendus_mois"] and not CONSOMMABLE.search(x["titre"])]
    montent.sort(key=lambda x: -(x["hausse"] * min(x["vendus_mois"], 2000)))
    print("ventes en hausse ≥ 25 % sur 15 jours :", len(montent), "sur", len(prods))
    top = montent[:30]
    # recherches Google : volume mensuel + courbe 30 jours
    reqs = {x["asin"]: requete(x["titre"]) for x in top}
    vol = dataforseo.volumes(list(reqs.values())) if top else {}
    tend = {}
    mots = list(dict.fromkeys(reqs.values()))
    for i in range(0, len(mots), 5):
        try:
            tend.update(dataforseo.tendances(mots[i:i + 5], periode="past_30_days"))
        except Exception as e:
            print("tendances", str(e)[:120])
    # chasse : Google Shopping (recherche par nom), même produit confirmé par l'IA, puis TOUS les vendeurs de la fiche Google
    gs = shopping.chercher([reqs[x["asin"]] for x in top], "FR", attente_max=240) if top else {}
    for x in top:
        q = reqs[x["asin"]]
        v = vol.get(q) or next((d for k, d in vol.items() if k.lower() == q.lower()), None) or {}
        x["requete"], x["volume"] = q, v.get("volume_mensuel")
        x["tendance"] = (tend.get(q) or {}).get("tendance")
        fiche = None
        for o in sorted(gs.get(q, []), key=lambda o: -(o.get("avis") or 0)):
            if o.get("product_id") and meme_produit.verifier(x["titre"], o["titre"], x["prix_amazon"], o["prix"])["meme"] is True:
                fiche = o; break
        x["fiche_google"] = fiche
    pids = [x["fiche_google"]["product_id"] for x in top if x.get("fiche_google")]
    vend = shopping.vendeurs(pids, "FR", attente_max=240) if pids else {}
    for x in top:
        f = x.get("fiche_google")
        vs = [v for v in vend.get(f["product_id"], [])] if f else []
        vs = [v for v in vs if v.get("etat") in (None, "", "new", "neuf") and not OCC.search(str(v.get("marchand") or ""))]
        for v in vs:
            v["total"] = v.get("total") or round(v["prix"] + (v.get("port") or 0), 2)
        vs.sort(key=lambda v: v["total"])
        x["vendeurs_gs"] = len({str(v.get("marchand")).lower() for v in vs}) if f else None
        x["moins_cher"] = vs[0] if vs else None
        x["ecart"] = round((1 - vs[0]["total"] / x["prix_amazon"]) * 100) if vs and x["prix_amazon"] else None
        x["anormal"] = x["ecart"] is not None and x["ecart"] >= 50   # souvent pas la même quantité : jamais gagnant sans vérification
    json.dump(prods, open("data/winners_tous.json", "w", encoding="utf-8"), ensure_ascii=False)
    rapport(top, len(prods))


def rapport(top, n_analyses):
    heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M")
    e = lambda s: H.escape(str(s)) if s is not None else "inconnu"  # noqa: E731
    lignes = ""
    for x in top:
        mc = x.get("moins_cher")
        chasse = (f"<a href='{e(mc.get('lien'))}'>{mc['total']} € port compris — {e(mc.get('marchand'))}</a><br><small>✅ même produit"
                  f"{' · ' + str(x['ecart']) + ' % sous Amazon' if x.get('ecart') is not None else ''}"
                  f"{' · ⚠️ écart anormal, vérifier la quantité' if x.get('anormal') else ''}</small>") if mc else "pas de vendeur pro moins cher trouvé"
        winner = 15 <= (x.get("ecart") or 0) < 50 and (x.get("offres_neuves") or 99) <= 15
        lignes += (f"<tr style='background:{'#d9f7d9' if winner else '#fff'}'><td>{e(x['cat'])}</td><td><a href='{x['lien']}'>{e(x['titre'])}</a></td>"
                   f"<td>{e(x['prix_amazon'])} €</td><td><b>×{x['hausse']}</b><br><small>rang {int(x['rang_15j'])} → {int(x['rang_now'])}</small></td>"
                   f"<td>{e(x['vendus_mois'])}{' (il y a 15 j : ' + str(x['vendus_mois_15j']) + ')' if x.get('vendus_mois_15j') else ''}</td>"
                   f"<td>{e(x.get('volume'))}<br><small>{e(x.get('tendance'))}</small></td><td>{e(x.get('offres_neuves'))} / {e(x.get('vendeurs_gs'))}</td>"
                   f"<td>{chasse}</td><td>{'🏆' if winner else ''}</td></tr>")
    page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Produits gagnants</title>
<style>body{{font-family:system-ui;margin:12px;background:#fff;color:#111}}table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}th{{background:#eee}}</style>
<h2>Produits dont les ventes montent — Amazon.fr, 15 derniers jours — {heure}</h2>
<p><b>Sources :</b> historique du classement des ventes Amazon.fr et « achetés le mois dernier » (Keepa) ; recherches Google (Google Ads, Google Trends 30 j) ;
vendeurs pros français (Google Shopping, produit contrôlé « même produit »). {n_analyses} produits analysés ; seuls ceux dont le classement de ventes s'est amélioré
d'au moins 25 % en 15 jours sont listés (×1,5 = se vend environ 1,5 fois plus qu'il y a 15 jours). Consommables exclus.
<b>🏆</b> = trouvé 15 à 50 % sous Amazon (port compris) chez un vendeur pro français, même produit confirmé, et 15 offres neuves ou moins sur Amazon. Prix Google Shopping à confirmer sur la page du vendeur avant tout achat.</p>
<table><tr><th>Catégorie</th><th>Produit (Amazon)</th><th>Prix Amazon</th><th>Hausse des ventes 15 j</th><th>Achetés le mois dernier</th><th>Recherches Google /mois</th>
<th>Offres Amazon / vendeurs Google</th><th>Moins cher trouvé</th><th></th></tr>{lignes}</table></html>"""
    open("data/winners.html", "w", encoding="utf-8").write(page)
    json.dump(top, open("data/winners.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for x in top:
        print(f"×{x['hausse']} | {x['vendus_mois']}/mois | {x['prix_amazon']} € | vol {x.get('volume')} {x.get('tendance')} | offres {x.get('offres_neuves')}/{x.get('vendeurs_gs')} | "
              f"moins cher {(x.get('moins_cher') or {}).get('total')} {(x.get('moins_cher') or {}).get('marchand')} ({x.get('ecart')} %) | {x['titre'][:70]}")


if __name__ == "__main__":
    main()
