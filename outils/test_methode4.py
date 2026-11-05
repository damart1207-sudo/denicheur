"""TEST MÉTHODE 4 (05/11) : candidats = produits de la page Black Friday de ManoMano (prix lus dans les DONNÉES de la page),
comparés au marché FRANÇAIS : fiche produit Google exacte -> vendeurs NEUFS français (domaine .fr ou enseigne française),
ManoMano lui-même exclu. Bingo = prix ManoMano ≥ 20 % sous le moins cher des autres marchands français.
Coût : 2 × 0,002 $ par produit.   Lancement : outil = test_methode4"""
import gzip, html as H, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import shopping, telegram, meme_produit  # noqa: E402
from pc.collecteur import extraire  # noqa: E402

import json
pc = json.load(open("data/pc/annonces.json")).get("annonces", [])
cands = [a for a in pc if a.get("prix_source") == "donnees_integrees" and a.get("etat") == "neuf"
         and a.get("source") in ("pc:manomano-blackfriday", "pc:manomano-bonsplans", "pc:cdiscount-meilleures-offres")][:60]
if not cands:  # secours : page enregistrée (liens masqués dans l'échantillon)
    h = gzip.open("data/echantillons/pc/manomano-blackfriday.html.gz", "rt", encoding="utf-8", errors="ignore").read()
    cands = [a for a in extraire(h, "manomano-blackfriday", "FR", "ManoMano", "https://www.manomano.fr") if a.get("etat") == "neuf"][:40]
print("candidats ManoMano", len(cands))
FR = re.compile(r"\.fr\b|amazon\.fr|cdiscount|fnac|darty|boulanger|leroy ?merlin|castorama|brico ?d[ée]p[ôo]t|bricoman|electro ?d[ée]p[ôo]t|"
                r"rue ?du ?commerce|ldlc|materiel\.net|carrefour|leclerc|auchan|conforama|\bbut\b|decathlon|micromania|cultura|lidl|"
                r"maisons du monde|la redoute|but\.fr|gifi|weldom|mr ?bricolage|point\.p|cedeo|leroy", re.I)
EXCLUS = re.compile(r"manomano|cdiscount_meme|leboncoin|ebay|vinted|stockx|back ?market|beebs|achatmoinscher|idealo|ledenicheur|occasion|reconditionn", re.I)


def requete(t):
    t = re.sub(r"[\[\(].*?[\]\)]", "", t)
    t = re.split(r" – | - |,", t)[0] if len(t) > 60 else t
    return " ".join(t.split()[:8])


res = shopping.chercher([requete(a["titre"]) for a in cands], "FR", attente_max=240)
fiches = {}
for a in cands:
    q = requete(a["titre"])
    mots = set(re.findall(r"[a-z0-9]{3,}", q.lower()))
    ok = [o for o in res.get(q, []) if o.get("product_id") and len(mots & set(re.findall(r"[a-z0-9]{3,}", (o["titre"] or "").lower()))) >= max(2, int(len(mots) * 0.6))]
    if ok:
        fiches[a["id"]] = max(ok, key=lambda o: (o.get("avis") or 0))
vend = shopping.vendeurs([f["product_id"] for f in fiches.values()], "FR", attente_max=240)
heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M")
rows, bingos = "", 0
for a in cands:
    f = fiches.get(a["id"])
    vs = []
    if f:
        for v in vend.get(f["product_id"], []):
            nom = f"{v.get('marchand') or ''} {v.get('lien') or ''}"
            meme = (a.get("marchand") or "x").split()[0].lower()  # le marchand de l'annonce lui-même est exclu de la comparaison
            if v.get("etat") in (None, "", "new", "neuf") and FR.search(nom) and not EXCLUS.search(nom) and meme not in nom.lower():
                v["total"] = v.get("total") or round(v["prix"] + (v.get("port") or 0), 2)
                vs.append(v)
    vs.sort(key=lambda v: v["total"])
    # MÊME PRODUIT ? (quantité, variante, caractéristiques) : on ne garde comme référence que des offres du même produit exact
    verif, vs_ok = [], []
    for v in vs[:4]:
        tb = (f or {}).get("titre") or ""
        if v.get("titre") and len(v["titre"]) > 15 and v["titre"].lower() != str(v.get("marchand") or "").lower():
            tb = v["titre"] if len(v["titre"]) > len(tb) else tb  # le titre du vendeur s'il est plus précis que la fiche
        r = meme_produit.verifier(a["titre"], tb, a["prix"], v["total"])
        v["meme"] = r
        if r["meme"] is not False:
            vs_ok.append(v)
        verif.append(f"{v.get('marchand')} : {'✅' if r['meme'] else '❌' if r['meme'] is False else '❓'} {r['raison']}")
    vs = vs_ok
    ecart = round((1 - a["prix"] / vs[0]["total"]) * 100) if vs else None
    bingo = ecart is not None and ecart >= 20 and vs[0]["meme"]["meme"] is True
    a["verif_txt"] = "<br>".join(verif)
    bingos += bingo
    autre = (f"<a href='{H.escape(vs[0].get('lien') or '#')}'>{vs[0]['total']} € — {H.escape(str(vs[0]['marchand']))}</a>"
             + (f"<br><small>2e : {vs[1]['total']} € — {H.escape(str(vs[1]['marchand']))}</small>" if len(vs) > 1 else "")) if vs else "aucun autre marchand français trouvé"
    rows += (f"<tr style='background:{'#d9f7d9' if bingo else '#fff'}'><td>{H.escape(a['titre'][:90])}</td><td><a href='{H.escape(a.get('lien') or '#')}'><b>{a['prix']} €</b> — {H.escape(a.get('marchand') or '')}</a><br><small>{H.escape(a['description'][:60])}</small></td>"
             f"<td>{H.escape((f or {}).get('titre') or '—')}<br><small>{a.get('verif_txt', '')}</small></td><td>{autre}</td><td>{len(vs)}</td><td>{(str(ecart) + ' %') if ecart is not None else '—'}</td><td><b>{'BINGO' if bingo else ''}</b></td></tr>")
    print(("BINGO " if bingo else "      ") + f"{a['prix']:>8} | {a['titre'][:45]:45s} | autres FR : {vs[0]['total'] if vs else '-'} ({vs[0]['marchand'] if vs else '-'}) | écart {ecart}")
page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Test méthode 4</title>
<style>body{{font-family:system-ui;margin:12px;background:#fff;color:#111}}table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}th{{background:#eee}}</style>
<h2>Test méthode 4 — Black Friday ManoMano comparé au marché français — {heure}</h2>
<p>Prix ManoMano lus dans les données de la page (pas à l'écran). Comparaison avec la fiche produit Google exacte, vendeurs NEUFS français uniquement
(ManoMano, occasion, revente et comparateurs exclus). <b>BINGO</b> = ManoMano ≥ 20 % moins cher que le moins cher des autres marchands français, ET même produit confirmé (quantité du lot, variante, caractéristiques ; ✅ confirmé, ❌ différent, ❓ non confirmé). Bingos : <b>{bingos}</b> sur {len(cands)}.</p>
<table><tr><th>Produit ManoMano</th><th>Prix ManoMano</th><th>Fiche Google retenue + contrôle « même produit »</th><th>Moins cher ailleurs en France (port compris)</th><th>Marchands FR</th><th>Écart</th><th>Verdict</th></tr>{rows}</table></html>"""
open("data/test_methode4.html", "w", encoding="utf-8").write(page)
print("BINGOS", bingos)
telegram.envoyer_fichier("data/test_methode4.html", f"Test méthode 4 ({heure}) : ManoMano Black Friday vs marché français — {bingos} bingos")
