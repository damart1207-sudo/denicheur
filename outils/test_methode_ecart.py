"""TEST MÉTHODE 2 (05/11) : partir de ce que les gens ACHÈTENT (150 produits les plus recherchés en France, liste du bingo),
demander à Google Shopping France TOUS les marchands et leurs prix (données, pas de lecture de page),
et repérer le marchand nettement moins cher que les autres (le cas Carrera ManoMano 64,90 € contre 159 € ailleurs).
Bingo = le moins cher est ≥ 20 % sous le 2e moins cher ET sous la médiane du marché.
Coût : 0,002 $ par produit (≈ 0,12 $ pour 60). -> data/test_methode_ecart.html (+ Telegram)   Lancement : outil = test_methode_ecart"""
import html as H, json, os, re, statistics, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import shopping, telegram  # noqa: E402

N = 60
produits = json.load(open("data/bingo.json"))["meilleurs"]
produits = [p for p in sorted(produits, key=lambda p: -(p.get("recherches_mois") or 0)) if p.get("mot_cle")][:N]
res = shopping.chercher([p["mot_cle"] for p in produits], "FR", attente_max=240)
print("requêtes", len(produits), "réponses", len(res))
lignes, bingos = [], 0
for p in produits:
    q = p["mot_cle"]
    mots = set(re.findall(r"[a-z0-9]{2,}", q.lower()))
    ref = p.get("prix") or 0
    OCCASION = re.compile(r"leboncoin|ebay|vinted|etsy|back ?market|rakuten|label emma|easy ?cash|cash converters|certideal|recommerce|swappie", re.I)
    PAS_LE_PRODUIT = re.compile(r"occasion|reconditionn|d.occasion|échantillon|echantillon|d[ée]cant|miniature|recharge|protège|protege|sleeve|housse|coque|"
                                r"support|câble|cable|chargeur|étui|etui|skin|sticker|pièce|piece|bracelet seul|compatible|pour (?!homme|femme)", re.I)
    brutes = [o for o in res.get(q, []) if mots <= set(re.findall(r"[a-z0-9]{2,}", (o["titre"] or "").lower())) and o["prix"] >= ref * 0.35]
    occasions = sorted([o for o in brutes if OCCASION.search(o.get("marchand") or "") or re.search(r"occasion|reconditionn", o["titre"] or "", re.I)], key=lambda o: o["prix"])
    p["occasion_min"] = occasions[0] if occasions else None
    offres = [o for o in brutes if not OCCASION.search(o.get("marchand") or "") and not PAS_LE_PRODUIT.search(o["titre"] or "")]
    # un prix par marchand (le plus bas)
    par = {}
    for o in offres:
        m = (o.get("marchand") or "?").lower()
        if m not in par or o["prix"] < par[m]["prix"]:
            par[m] = o
    o = sorted(par.values(), key=lambda o: o["prix"])
    if len(o) < 3:
        lignes.append((p, o, None, "pas assez de marchands comparables"))
        continue
    med = statistics.median(x["prix"] for x in o)
    ecart2 = round((1 - o[0]["prix"] / o[1]["prix"]) * 100)
    ecartm = round((1 - o[0]["prix"] / med) * 100)
    bingo = ecart2 >= 20 and ecartm >= 20
    bingos += bingo
    lignes.append((p, o, (ecart2, ecartm, med), "BINGO" if bingo else ""))
    if p.get("occasion_min"):
        print(f"      occasion la moins chère : {p['occasion_min']['prix']} ({p['occasion_min']['marchand']})")
    print(("BINGO " if bingo else "      ") + f"{q[:30]:30s} 1er {o[0]['prix']} ({o[0]['marchand']}) 2e {o[1]['prix']} méd {med} | écart 2e {ecart2} %")
rows = ""
for p, o, e, v in lignes:
    if not o:
        rows += f"<tr><td>{H.escape(p['mot_cle'])}</td><td colspan=6>{v}</td></tr>"
        continue
    l0 = f"<a href='{H.escape(o[0].get('lien') or '#')}'>{o[0]['prix']} € — {H.escape(str(o[0].get('marchand')))}</a>"
    l1 = f"<a href='{H.escape(o[1].get('lien') or '#')}'>{o[1]['prix']} € — {H.escape(str(o[1].get('marchand')))}</a>" if len(o) > 1 else "—"
    rows += (f"<tr style='background:{'#d9f7d9' if v == 'BINGO' else '#fff'}'><td>{H.escape(p['mot_cle'])}<br><small>{p.get('recherches_mois')} rech./mois</small></td>"
             f"<td>{l0}<br><small>{H.escape(o[0]['titre'][:70])}</small></td><td>{l1}</td><td>{e[2] if e else '—'} €</td>"
             f"<td>{(str(e[0]) + ' %') if e else '—'}</td><td>{len(o)}</td><td><b>{v}</b></td>"
             f"<td>{(str(p['occasion_min']['prix']) + ' € — ' + H.escape(str(p['occasion_min']['marchand']))) if p.get('occasion_min') else '—'}</td></tr>")
page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Test méthode 2</title>
<style>body{{font-family:system-ui;margin:12px;background:#fff;color:#111}}table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}th{{background:#eee}}</style>
<h2>Test méthode 2 — écart entre marchands (Google Shopping France) — {datetime.now(timezone.utc).strftime('%d/%m %H:%M')} UTC</h2>
<p>{len(produits)} produits parmi les plus recherchés en France. Pour chacun : tous les marchands trouvés par Google Shopping (même produit),
uniquement les offres NEUVES de vrais marchands (occasion, Leboncoin, eBay, Etsy, accessoires et échantillons écartés), le moins cher, le 2e moins cher, la médiane. L'occasion la moins chère est indiquée à part. <b>BINGO</b> = le moins cher est au moins 20 % sous le 2e ET sous la médiane. Bingos : <b>{bingos}</b>.
<br>À vérifier par David : cliquer les liens et confirmer les prix.</p>
<table><tr><th>Produit</th><th>Le moins cher</th><th>2e moins cher</th><th>Médiane</th><th>Écart avec le 2e</th><th>Marchands (neuf)</th><th>Verdict</th><th>Occasion la moins chère</th></tr>{rows}</table></html>"""
open("data/test_methode_ecart.html", "w", encoding="utf-8").write(page)
print("BINGOS", bingos)
telegram.envoyer_fichier("data/test_methode_ecart.html", f"Test méthode 2 : {bingos} bingos sur {len(produits)} produits — à vérifier")
