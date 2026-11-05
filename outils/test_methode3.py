"""TEST MÉTHODE 3 (05/11, après les retours de David sur la Switch) :
 1. Google Shopping : recherche du produit -> on choisit la FICHE PRODUIT Google (product_id) dont le titre correspond
    exactement à la recherche et qui a le plus d'avis (le produit « standard », pas un pack / une version JP / une extension) ;
 2. vendeurs de CETTE fiche (même produit regroupé par Google) : prix + port, neuf seulement ;
 3. contrôle sur la page du marchand (données structurées) quand le site le permet depuis GitHub ;
 4. bingo = le moins cher (port compris) ≥ 15 % sous le 2e moins cher.
Coût : 2 × 0,002 $ par produit (≈ 0,08 $ pour 20).  -> data/test_methode3.html (+ Telegram)   Lancement : outil = test_methode3"""
import html as H, json, os, re, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import shopping, telegram, verif_prix  # noqa: E402

N = 20
VERSIONS = re.compile(r"\b(jp|japon|japan|us|usa|import|uk|asia|asie|hk|cn)\b|version (jp|us|uk|asiatique|japonaise)", re.I)
PAS_LE_PRODUIT = re.compile(r"\+|pack|bundle|lot de|dlc|extension|expansion|season pass|cl[ée] |code|carte cadeau|occasion|reconditionn|"
                            r"coque|housse|étui|etui|protège|protege|câble|cable|chargeur|support|sticker|skin|compatible", re.I)
produits = [p for p in sorted(json.load(open("data/bingo.json"))["meilleurs"], key=lambda p: -(p.get("recherches_mois") or 0)) if p.get("mot_cle")][:N]
recherche = shopping.chercher([p["mot_cle"] for p in produits], "FR", attente_max=240)
fiches = {}
for p in produits:
    q = p["mot_cle"]
    mots = set(re.findall(r"[a-z0-9]{2,}", q.lower()))
    cands = [o for o in recherche.get(q, []) if o.get("product_id") and mots <= set(re.findall(r"[a-z0-9]{2,}", (o["titre"] or "").lower()))
             and not PAS_LE_PRODUIT.search(o["titre"] or "") and not VERSIONS.search(o["titre"] or "")]
    if cands:
        best = max(cands, key=lambda o: (o.get("avis") or 0, -len(o["titre"] or "")))
        fiches[q] = best
print("fiches retenues", len(fiches), "sur", len(produits))
vend = shopping.vendeurs([f["product_id"] for f in fiches.values()], "FR", attente_max=240)
heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M")
lignes, bingos = [], 0
occ_info = {}
for p in produits:
    q = p["mot_cle"]
    f = fiches.get(q)
    if not f:
        lignes.append((q, None, [], None, "fiche produit exacte non trouvée"))
        continue
    PAS_MARCHAND = re.compile(r"leboncoin|ebay|vinted|stockx|back ?market|rakuten|beebs|achatmoinscher|idealo|ledenicheur|kelkoo|"
                              r"cherchons|touslesprix|prixing|occasion|reconditionn", re.I)  # occasion, revente, comparateurs
    vs = [v for v in vend.get(f["product_id"], []) if (v.get("etat") in (None, "", "new", "neuf")) and not VERSIONS.search(v.get("titre") or "")
          and not PAS_MARCHAND.search(str(v.get("marchand") or ""))]
    for v in vs:
        v["total"] = v.get("total") or round(v["prix"] + (v.get("port") or 0), 2)
    vs.sort(key=lambda v: v["total"])
    # OCCASION comparée à l'OCCASION seulement (Leboncoin, eBay, Vinted, Back Market… ou état « used »)
    occ = [v for v in vend.get(f["product_id"], []) if (v.get("etat") not in (None, "", "new", "neuf"))
           or re.search(r"leboncoin|ebay|vinted|back ?market|rebuy|beebs|occasion|reconditionn", str(v.get("marchand") or ""), re.I)]
    for v in occ:
        v["total"] = v.get("total") or round(v["prix"] + (v.get("port") or 0), 2)
    occ.sort(key=lambda v: v["total"])
    occ_info[q] = occ
    if len(vs) < 2:
        lignes.append((q, f, vs, None, "moins de 2 vendeurs neufs"))
        continue
    for v in vs[:2]:  # contrôle sur la page du marchand (si le site laisse GitHub lire la page)
        c = verif_prix.controler({"lien": v.get("lien") or "", "prix": v["prix"]})
        v["controle"] = c
    ecart = round((1 - vs[0]["total"] / vs[1]["total"]) * 100)
    bingo = ecart >= 15 and (vs[0]["controle"]["statut"] != "different")
    bingos += bingo
    lignes.append((q, f, vs, ecart, "BINGO" if bingo else ""))
    print(("BINGO " if bingo else "      ") + f"{q[:28]:28s} | fiche « {f['titre'][:45]} » | 1er {vs[0]['total']} ({vs[0]['marchand']}, page {vs[0]['controle']['statut']} {vs[0]['controle'].get('prix_page')}) | 2e {vs[1]['total']} ({vs[1]['marchand']}) | écart {ecart} %")


def cel(v):
    if not v:
        return "—"
    c = v.get("controle") or {}
    etat = {"ok": f"✅ page : {c.get('prix_page')} €", "different": f"❌ page : {c.get('prix_page')} €", "inconnu": "⚠️ page non lisible depuis le cloud"}.get(c.get("statut"), "")
    port = f" + port {v['port']} €" if v.get("port") else ""
    return (f"<a href='{H.escape(v.get('lien') or '#')}'>{v['prix']} €{port} = <b>{v['total']} €</b> — {H.escape(str(v.get('marchand')))}</a><br><small>{etat}</small>")


def occ_txt(o):
    if not o:
        return "—"
    t = f"{o[0]['total']} € — {H.escape(str(o[0].get('marchand')))}"
    if len(o) > 1:
        ec = round((1 - o[0]['total'] / o[1]['total']) * 100)
        t += f"<br><small>2e occasion : {o[1]['total']} € ({ec} % d'écart){' — <b>BON PLAN OCCASION</b>' if ec >= 20 else ''}</small>"
    return t


rows = "".join(f"<tr style='background:{'#d9f7d9' if v == 'BINGO' else '#fff'}'><td>{H.escape(q)}</td><td>{H.escape((f or {}).get('titre') or '—')}</td>"
               f"<td>{cel(vs[0] if vs else None)}</td><td>{cel(vs[1] if len(vs) > 1 else None)}</td><td>{len(vs)}</td>"
               f"<td>{(str(e) + ' %') if e is not None else '—'}</td><td><b>{v}</b></td><td>{occ_txt(occ_info.get(q, []))}</td></tr>" for q, f, vs, e, v in lignes)
page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Test méthode 3</title>
<style>body{{font-family:system-ui;margin:12px;background:#fff;color:#111}}table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}th{{background:#eee}}</style>
<h2>Test méthode 3 — fiche produit exacte + vendeurs + contrôle page — {heure} (Paris)</h2>
<p>Pour chaque produit : la fiche produit Google exacte (pas de pack, pas de version JP/US, pas d'extension), ses vendeurs NEUFS, prix + port.
Le moins cher et le 2e sont relus sur la page du marchand quand c'est possible (✅ même prix, ❌ prix différent, ⚠️ page bloquée pour le cloud :
c'est le PC qui la vérifiera). <b>BINGO</b> = le moins cher, port compris, ≥ 15 % sous le 2e. Comparaison à état égal : le neuf de professionnel avec le neuf de professionnel uniquement ; l'occasion avec l'occasion uniquement (colonne de droite). Bingos : <b>{bingos}</b>.</p>
<table><tr><th>Recherche</th><th>Fiche produit retenue</th><th>Le moins cher (port compris)</th><th>2e moins cher</th><th>Vendeurs neufs</th><th>Écart (neuf/neuf)</th><th>Verdict neuf</th><th>Occasion (comparée à l'occasion)</th></tr>{rows}</table></html>"""
open("data/test_methode3.html", "w", encoding="utf-8").write(page)
print("BINGOS", bingos)
telegram.envoyer_fichier("data/test_methode3.html", f"Test méthode 3 ({heure}) : {bingos} bingos sur {len(produits)} — à vérifier")
