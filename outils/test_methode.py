"""TEST DE LA NOUVELLE MÉTHODE (05/11, demandé par David) — uniquement des données chiffrées, aucune lecture de page :
 1. Keepa /deal : baisses de prix Amazon France + Allemagne (≥ 40 % sous la moyenne 90 j, calculée par nous) ;
 2. Keepa /product : EAN + prix actuel (relecture) ;
 3. Google Shopping France (DataForSEO, file prioritaire) : tous les marchands et leurs prix pour cet EAN ;
 4. verdict : le prix Amazon est-il confirmé par Google Shopping (2 sources d'accord) ? est-il sous le prix le plus bas
    des AUTRES marchands en France ?
Coût : ≈ 10 + 30 jetons Keepa, ≈ 15 × 0,002 $ DataForSEO. -> data/test_methode.html (+ envoi Telegram)
Lancement : outil = test_methode"""
import html as H
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import moisson, shopping, telegram  # noqa: E402

N = 15
deals = []
for domaine, pays in ((4, "FR"), (3, "DE")):
    sel = {"page": 0, "domainId": domaine, "priceTypes": [1], "dateRange": 0, "isFilterEnabled": True, "isRangeEnabled": True,
           "deltaPercentRange": [30, 95], "currentRange": [3000, 150000], "salesRankRange": [1, 20000],
           "singleVariation": True, "filterErotic": True, "hasReviews": True, "isLowest90": True, "minRating": 40}
    try:
        d = moisson._appel("deal", {"domain": domaine}, corps=sel)
    except Exception as e:
        print("deal", pays, "ERREUR", e)
        continue
    for x in (d.get("deals") or {}).get("dr") or []:
        cur, avg = x.get("current") or [], x.get("avg") or []
        prix = moisson._prix(cur[1]) if len(cur) > 1 else None
        try:
            m90 = moisson._prix(avg[3][1])
        except (IndexError, TypeError):
            m90 = None
        if prix and m90 and m90 > prix:
            baisse = round((m90 - prix) / m90 * 100)
            if baisse >= 30:
                deals.append({"asin": x["asin"], "titre": x.get("title"), "pays": pays, "prix_keepa": prix, "moy90": m90, "baisse": baisse})
    print("deals", pays, len((d.get("deals") or {}).get("dr") or []), "-> ≥40 % :", sum(1 for z in deals if z["pays"] == pays))

deals.sort(key=lambda z: -z["baisse"])
# fiche Keepa de toutes les baisses : marque connue + note, sinon c'est souvent un faux prix barré d'un produit sans marque
for pays in ("FR", "DE"):
    fi = {r["asin"]: r for r in moisson.fiches([z["asin"] for z in deals if z["pays"] == pays][:100], pays)}
    for z in deals:
        if z["pays"] == pays and z["asin"] in fi:
            r = fi[z["asin"]]
            z["marque"], z["note"], z["m180"] = r.get("marque"), r.get("note"), r.get("m180")
import re as _re
def _serieux(z):
    m = (z.get("marque") or "").strip()
    return bool(m) and len(m) > 2 and not _re.fullmatch(r"[A-Z]{5,}|generic|générique|unbranded|sans marque", m, _re.I) \
        and (not z.get("m180") or z["m180"] < z["moy90"] * 1.5)  # moyenne 90 j pas gonflée par rapport aux 180 j
serieux = [z for z in deals if _serieux(z)]
print("marques sérieuses :", len(serieux), "sur", len(deals))
choix = serieux[:N]
for pays in ("FR", "DE"):
    asins = [z["asin"] for z in choix if z["pays"] == pays]
    for r in moisson.fiches(asins, pays):
        for z in choix:
            if z["asin"] == r["asin"] and z["pays"] == pays:
                z["ean"], z["prix_relu"], z["vendeurs"] = r.get("ean"), r.get("neuf"), r.get("offres")
# le même produit sur Amazon.fr (pour les affaires allemandes)
de = [z for z in choix if z["pays"] == "DE"]
for r in moisson.fiches([z["asin"] for z in de], "FR"):
    for z in de:
        if z["asin"] == r["asin"]:
            z["prix_amazon_fr"] = r.get("neuf")

res = shopping.chercher([z.get("ean") or (z["titre"] or "")[:60] for z in choix], "FR")
for z in choix:
    q = z.get("ean") or (z["titre"] or "")[:60]
    mots = set(_re.findall(r"[a-z0-9]{3,}", ((z.get("marque") or "") + " " + (z["titre"] or "")[:70]).lower()))
    def _meme(o):  # même produit : au moins la moitié des mots importants en commun, prix plausible (pas un accessoire)
        mo = set(_re.findall(r"[a-z0-9]{3,}", (o["titre"] or "").lower()))
        p = z.get("prix_relu") or z["prix_keepa"]
        return len(mots & mo) >= max(2, len(mots) // 2) and o["prix"] >= p * 0.4
    offres = sorted([o for o in res.get(q, []) if _meme(o)], key=lambda o: o["prix"])
    z["gs_nb"] = len(offres)
    amz = [o for o in offres if "amazon" in (o.get("marchand") or "").lower()]
    autres = [o for o in offres if "amazon" not in (o.get("marchand") or "").lower()]
    z["gs_amazon"] = amz[0]["prix"] if amz else None
    z["gs_min_autres"] = autres[0] if autres else None
    p = z.get("prix_relu") or z["prix_keepa"]
    z["deux_sources"] = bool(z["gs_amazon"] and abs(z["gs_amazon"] - p) / p <= 0.05) if z["pays"] == "FR" else None
    ref = z["gs_min_autres"]["prix"] if z["gs_min_autres"] else None
    z["ecart_vs_france"] = round((1 - p / ref) * 100) if ref else None

lignes = []
for z in choix:
    m = z.get("gs_min_autres") or {}
    lien_amz = f"https://www.amazon.{'fr' if z['pays'] == 'FR' else 'de'}/dp/{z['asin']}"
    deux = {True: "✅ oui", False: "❌ non", None: "—"}[z.get("deux_sources")]
    lignes.append(f"<tr><td>{H.escape((z['titre'] or '')[:80])}</td><td>{z['pays']}</td>"
                  f"<td><a href='{lien_amz}'>{z.get('prix_relu') or z['prix_keepa']} €</a></td><td>{z['moy90']} €</td><td>-{z['baisse']} %</td>"
                  f"<td>{z.get('ean') or '—'}</td><td>{z.get('gs_amazon') or '—'}</td><td>{deux}</td>"
                  f"<td>{m.get('prix', '—')} € {H.escape(str(m.get('marchand') or ''))}"
                  + (f" <a href='{H.escape(m['lien'])}'>lien</a>" if m.get("lien") else "") + f"</td><td>{z['gs_nb']}</td>"
                  f"<td>{(str(z['ecart_vs_france']) + ' %') if z.get('ecart_vs_france') is not None else '—'}</td>"
                  f"<td>{z.get('prix_amazon_fr') or ''}</td></tr>")
page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test méthode données chiffrées</title><style>body{{font-family:system-ui;margin:12px;background:#fff;color:#111}}
table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}th{{background:#eee}}</style>
<h2>Test de la nouvelle méthode — {datetime.now(timezone.utc).strftime('%d/%m %H:%M')} UTC</h2>
<p>Sources : Keepa (prix Amazon en données) + Google Shopping France (tous les marchands, en données). Aucune page lue.
« 2 sources d'accord » = le prix Keepa est confirmé par l'offre Amazon vue dans Google Shopping (±5 %).
« Écart vs France » = notre prix comparé au moins cher des AUTRES marchands en France (positif = on est moins cher).</p>
<p>Baisses ≥ 40 % trouvées : {len(deals)} (FR {sum(1 for z in deals if z['pays']=='FR')}, DE {sum(1 for z in deals if z['pays']=='DE')}). Testées ici : {len(choix)}.</p>
<table><tr><th>Produit</th><th>Pays</th><th>Prix Keepa (lien)</th><th>Moy. 90 j</th><th>Baisse</th><th>EAN</th><th>Amazon dans G. Shopping</th>
<th>2 sources</th><th>Moins cher ailleurs en France</th><th>Nb offres</th><th>Écart vs France</th><th>Amazon.fr (si DE)</th></tr>{''.join(lignes)}</table></html>"""
os.makedirs("data", exist_ok=True)
open("data/test_methode.html", "w", encoding="utf-8").write(page)
json.dump(choix, open("data/test_methode.json", "w"), ensure_ascii=False, indent=1)
print("OK", len(choix))
for z in choix:
    print(" ", z["pays"], z.get("prix_relu") or z["prix_keepa"], "-", z["baisse"], "%", "| GS amazon", z.get("gs_amazon"), "| autres min", (z.get("gs_min_autres") or {}).get("prix"), "| écart", z.get("ecart_vs_france"), "|", (z["titre"] or "")[:50])
telegram.envoyer_fichier("data/test_methode.html", "Test de la nouvelle méthode (données chiffrées) : à vérifier")
