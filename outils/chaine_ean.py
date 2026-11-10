"""CHAÎNE EAN, les deux dénicheurs (10/11/2026). Aucun envoi Telegram : le résultat est audité avant d'être montré.
  Idéfix (bleu)  : bons plans français du jour -> fiche du marchand -> EAN + prix confirmé -> marché français par code.
  Amigo  (jaune) : produits qui se vendent (ventes Amazon 30 j, Keepa) -> marchand le moins cher par code.
Coût : Keepa 1 jeton par produit ; Google Shopping 0,004 $ par produit retenu (plafond du jour respecté par dataforseo).
Lancement : workflow « Dénicheur », outil = chaine_ean      Résultat : data/chaine.json + data/chaine.html"""
import collections
import html as H
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import chaine, dataforseo, lecteur, validation  # noqa: E402

DEBUT = time.monotonic()
BUDGET_S = 38 * 60                 # le lancement est coupé à 58 min : on s'arrête de soi-même bien avant
MAX_IDEFIX = int(os.environ.get("CHAINE_MAX_IDEFIX", "170"))
MAX_AMIGO = int(os.environ.get("CHAINE_MAX_AMIGO", "45"))
SOURCES_FR = ("dealabs-nouveaux", "dealabs-tendance", "dealabs-hot", "telegram:promorat", "telegram:bonsplans", "ldlc-promos")
regles = json.load(open("config/regles.json", encoding="utf-8"))


def reste():
    return BUDGET_S - (time.monotonic() - DEBUT)


def lire(f, d):
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return d


# ================================================================== IDÉFIX : promo -> demande
rec = lire("data/etat/annonces_recentes.json", [])
vus, cands = set(), []
for a in sorted(rec, key=lambda a: a.get("t") or "", reverse=True):
    if a.get("source") not in SOURCES_FR or a.get("devise", "EUR") != "EUR" or a.get("lien") in vus:
        continue
    if not isinstance(a.get("prix"), (int, float)) or not (chaine.PRIX_MIN <= a["prix"] <= chaine.PRIX_MAX):
        continue
    vus.add(a["lien"])
    cands.append({"denicheur": "Idéfix", "titre": a["titre"], "prix_annonce": a["prix"], "lien": a["lien"], "source": a["source"], "vu": a.get("t")})
# on mélange les sources (une sur deux) pour que la première mesure couvre tous les types de liens
par_source = collections.defaultdict(list)
for c in cands:
    par_source[c["source"]].append(c)
melange = []
while any(par_source.values()) and len(melange) < MAX_IDEFIX:
    for s in list(par_source):
        if par_source[s] and len(melange) < MAX_IDEFIX:
            melange.append(par_source[s].pop(0))
cands = melange
print(f"Idéfix : {len(cands)} candidats (sur {len(vus)} bons plans français du jour entre {chaine.PRIX_MIN} et {chaine.PRIX_MAX} €)")

for i, c in enumerate(cands):
    if reste() < 22 * 60:
        c["rejet"] = "non traité (temps écoulé)"
        continue
    try:
        chaine.identifier(c)
    except Exception as e:
        c["rejet"] = f"erreur de lecture ({type(e).__name__})"
    if i % 20 == 19:
        print(f"  identification {i + 1}/{len(cands)}")

# Amazon : ASIN -> EAN + prix par Keepa (1 jeton par produit, par lots de 50)
amz = [c for c in cands if c.get("asin") and not c.get("rejet")]
fiches_asin = {}
for i in range(0, len(amz), 50):
    fiches_asin.update(chaine.keepa_lot([c["asin"] for c in amz[i:i + 50]], "asin", "FR"))
for c in amz:
    k = fiches_asin.get(c["asin"])
    if not k:
        c["rejet"] = "fiche Amazon introuvable chez Keepa"
        continue
    c["keepa"] = k
    c["titre_fiche"] = k.get("titre")
    if not k.get("eans"):
        c["rejet"] = "produit Amazon sans code EAN"
    elif not k.get("prix_neuf"):
        c["rejet"] = "pas d'offre neuve sur Amazon en ce moment"
    else:
        c["ean"], c["prix_page"] = k["eans"][0], k["prix_neuf"]

# PC de David : pages de magasins illisibles depuis le cloud. On ne prend que les fiches RELUES par le PC aujourd'hui,
# avec le code EAN et le prix lus dans les données de la fiche (pc/collecteur.py, verifier_fiches).
pc = lire("data/pc/annonces.json", {})
jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
pc_frais = [a for a in pc.get("annonces", []) if (a.get("date") or "")[:10] == jour]
nb_pc = 0
for a in pc_frais:
    e = chaine.ean13(a.get("ean"))
    pv = a.get("preuve_prix") or {}
    if any(m in (a.get("source") or "") for m in ("occasion", "warehouse", "easycash", "leboncoin", "stockx", "emmaus", "rebuy", "vinted", "agorastore")):
        continue   # sources d'occasion : jamais comparées à du neuf
    if not e or a.get("prix_verifie") is not True or not pv.get("prix_page") or a.get("etat") not in (None, "neuf"):
        continue
    if not (chaine.PRIX_MIN <= pv["prix_page"] <= chaine.PRIX_MAX):
        continue
    nb_pc += 1
    cands.append({"denicheur": "Idéfix", "titre": a["titre"], "titre_fiche": a["titre"], "prix_annonce": a.get("prix_carte") or a["prix"],
                  "lien": a["lien"], "lien_marchand": a["lien"], "domaine": chaine.domaine(a["lien"]), "source": a.get("source"),
                  "ean": e, "prix_page": pv["prix_page"], "vu": pv.get("verifie_le"), "lu_par": "PC"})
print(f"PC : dernière collecte {pc.get('maj')}, {len(pc_frais)} annonces du jour, {nb_pc} fiches avec code EAN et prix relus")

identifies = [c for c in cands if c.get("ean") and c.get("prix_page") and not c.get("rejet")]
for c in identifies:
    c["achat"] = c["prix_page"]
    if not validation.meme_prix(c["prix_page"], c["prix_annonce"]):
        c["note_prix"] = (f"le bon plan annonçait {c['prix_annonce']} € (code promo, carte de fidélité ou remboursement différé ?) ; "
                          f"prix réellement affiché sur la fiche : {c['prix_page']} €")
print(f"Idéfix : {len(identifies)} produits identifiés par code avec prix confirmé")

# ================================================================== AMIGO : demande -> promo
idx = lire("data/base/keepa_index.json", {})
limite = (datetime.now(timezone.utc) - timedelta(days=6)).strftime("%Y-%m-%d")
amigo, vus_e = [], {c["ean"] for c in identifies}
for cle, r in sorted(idx.items(), key=lambda kv: -(kv[1].get("ch30") or 0)):
    if not cle.endswith(":FR") or (r.get("vu") or "") < limite or not chaine.ean13(r.get("ean")):
        continue
    if not isinstance(r.get("neuf"), (int, float)) or not (25 <= r["neuf"] <= 400) or (r.get("ch30") or 0) < 30 or (r.get("offres") or 99) > 8:
        continue
    e = chaine.ean13(r["ean"])
    if e in {a["ean"] for a in amigo}:
        continue
    amigo.append({"denicheur": "Amigo", "titre": r.get("t"), "titre_fiche": r.get("t"), "ean": e, "asin": cle.split(":")[0],
                  "ventes_30j": r.get("ch30"), "vendeurs_amazon": r.get("offres"), "amazon_index": r["neuf"], "source": "ventes Amazon (Keepa)"})
    if len(amigo) >= MAX_AMIGO:
        break
print(f"Amigo : {len(amigo)} produits qui se vendent (≥ 30 ventes estimées / 30 jours, ≤ 8 vendeurs Amazon)")

# ================================================================== marché français PAR CODE (les deux dénicheurs)
tous = {c["ean"]: c for c in amigo}
tous.update({c["ean"]: c for c in identifies})
eans = list(tous)
print(f"Google Shopping : {len(eans)} codes, coût prévu ≤ {len(eans) * 0.004:.2f} $ ; disponible : {dataforseo.disponible(len(eans) * 0.004)}")
marche = chaine.marche_google(eans, {e: c.get("titre_fiche") or c.get("titre") for e, c in tous.items()},
                              {e: (c.get("keepa") or {}).get("marque") or (c.get("fiche_page") or {}).get("marque") for e, c in tous.items()}) if eans else {}
print("Google Shopping : fiches trouvées", sum(1 for m in marche.values() if m.get("fiche")), "sur", len(eans))

# Amazon par code pour les produits identifiés hors Amazon (référence Amazon + ventes + vendeurs)
hors = [c["ean"] for c in identifies if not c.get("keepa")]
par_ean = {}
for i in range(0, len(hors), 50):
    par_ean.update(chaine.keepa_lot(hors[i:i + 50], "code", "FR"))
for c in identifies:
    if not c.get("keepa") and par_ean.get(c["ean"]):
        c["keepa"] = par_ean[c["ean"]]


def references(c, sauf):
    """Les AUTRES marchands français (Google) + Amazon (Keepa), sans le marchand où l'on achète."""
    m = marche.get(c["ean"]) or {}
    refs = [v for v in m.get("vendeurs", []) if sauf not in chaine.domaine(v.get("lien") or "") and sauf.split(".")[0] not in v["marchand"].lower()]
    k = c.get("keepa") or {}
    if k.get("prix_neuf") and "amazon" not in sauf and not any("amazon" in r["marchand"].lower() for r in refs):
        refs.append({"marchand": "Amazon.fr", "total": k["prix_neuf"], "gros": True, "lien": k.get("lien")})
    return refs, m


affaires = []
for c in identifies:
    refs, m = references(c, c["domaine"])
    k = c.get("keepa") or {}
    c["fiche_google"], c["marche_raison"], c["google_refuse"] = m.get("fiche"), m.get("raison"), m.get("refusees")
    gros = bool(chaine.GROS.search(c["domaine"]))
    if "amazon" in c["domaine"] and k.get("moyenne_90j"):
        # la promo Amazon finie, le prix revient à son niveau habituel : c'est lui, le vrai prix de revente possible
        refs.append({"marchand": "Amazon.fr (prix habituel sur 90 jours)", "total": k["moyenne_90j"], "gros": False, "lien": k.get("lien")})
    c["verdict"] = chaine.verdict(c["achat"], refs, True, regles, k.get("ventes_mois") or k.get("ventes_estimees_30j"))
    if gros and c["verdict"]["feu"] != "rouge":
        # tant que la promo dure, le client la voit aussi chez ce gros site : pas de livraison directe possible
        c["verdict"]["manque"].append("promo chez un gros site visible de tous : seulement en achat de stock, à revendre une fois la promo finie")
        c["verdict"]["feu"] = "orange"
    c["refs"] = refs[:6]
    affaires.append(c)

finalistes = []
for c in amigo:
    m = marche.get(c["ean"]) or {}
    vs = list(m.get("vendeurs", []))
    if c.get("amazon_index") and not any("amazon" in v["marchand"].lower() for v in vs):
        vs.append({"marchand": "Amazon.fr", "total": c["amazon_index"], "gros": True, "lien": f"https://www.amazon.fr/dp/{c['asin']}"})
    vs.sort(key=lambda v: v["total"])
    c["fiche_google"], c["marche_raison"], c["google_refuse"] = m.get("fiche"), m.get("raison"), m.get("refusees")
    if len(vs) < 2:
        c["verdict"] = {"feu": "rouge", "raison": m.get("raison") or "moins de deux marchands français pour ce code", "nb_vendeurs": len(vs)}
        affaires.append(c)
        continue
    moins_cher, autres = vs[0], vs[1:]
    c.update({"achat": moins_cher["total"], "marchand": moins_cher["marchand"], "lien_marchand": moins_cher.get("lien"),
              "domaine": chaine.domaine(moins_cher.get("lien") or ""), "refs": autres[:6]})
    c["verdict"] = chaine.verdict(c["achat"], autres, False, regles, c.get("ventes_30j"))
    if c["verdict"]["feu"] != "rouge":
        finalistes.append(c)
    affaires.append(c)

# Amigo : le prix du marchand le moins cher vient de Google (parfois en retard) -> relu dans les données de sa fiche
for c in finalistes:
    if reste() < 3 * 60 or not c.get("lien_marchand") or "amazon" in c["domaine"]:
        continue
    try:
        code, fin, h = lecteur._get(c["lien_marchand"])
        f = chaine.lire_fiche(h, c["ean"]) if code == 200 else {"raison": f"fiche illisible depuis le cloud ({code})"}
    except Exception as e:
        f = {"raison": f"erreur de lecture ({type(e).__name__})"}
    c["fiche_page"] = f
    if f.get("prix") and f.get("etat") == "neuf":
        c["achat"] = f["prix"]
        c["verdict"] = chaine.verdict(f["prix"], c["refs"], True, regles, c.get("ventes_30j"))
    else:
        c["verdict"].setdefault("manque", []).append(f"fiche du marchand : {f.get('raison') or 'produit pas neuf'}")

# étoile : le même code sort vert/orange des deux côtés
bons = collections.defaultdict(set)
for c in affaires:
    if (c.get("verdict") or {}).get("feu") in ("vert", "orange"):
        bons[c["ean"]].add(c["denicheur"])
for c in affaires:
    c["etoile"] = len(bons.get(c.get("ean"), ())) == 2

# ================================================================== résultat
ent = collections.OrderedDict()
ent["Idéfix — bons plans français du jour examinés"] = len(cands)
ent["Idéfix — lien du marchand trouvé"] = sum(1 for c in cands if c.get("lien_marchand"))
ent["Idéfix — produit identifié par code EAN, prix confirmé"] = len(identifies)
ent["   dont fiches lues par le PC (magasins fermés au cloud)"] = nb_pc
ent["Idéfix — marché français trouvé pour ce code"] = sum(1 for c in identifies if (c["verdict"].get("ref_min")))
ent["Amigo — produits qui se vendent examinés"] = len(amigo)
ent["Amigo — au moins deux marchands français pour ce code"] = sum(1 for c in amigo if c.get("achat"))
for d in ("Idéfix", "Amigo"):
    for feu in ("vert", "orange", "rouge"):
        ent[f"{d} — {feu}"] = sum(1 for c in affaires if c["denicheur"] == d and c["verdict"]["feu"] == feu)
rejets = collections.Counter((c.get("rejet") or "").split(" (")[0] for c in cands if c.get("rejet"))
par_dom = collections.defaultdict(lambda: [0, 0])
for c in cands:
    if c.get("domaine"):
        par_dom[c["domaine"]][0] += 1
        par_dom[c["domaine"]][1] += bool(c.get("ean") and not c.get("rejet"))
raisons_rouges = collections.Counter(c["verdict"].get("raison", "").split(" (")[0] for c in affaires if c["verdict"]["feu"] == "rouge")
heure = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M")
res = {"maj": heure, "entonnoir": ent, "rejets_identification": dict(rejets.most_common()),
       "raisons_rouges": dict(raisons_rouges.most_common()),
       "marchands": {d: {"vus": v[0], "identifies": v[1]} for d, v in sorted(par_dom.items(), key=lambda kv: -kv[1][0])},
       "affaires": sorted(affaires, key=lambda c: ({"vert": 0, "orange": 1, "rouge": 2}[c["verdict"]["feu"]], -(c["verdict"].get("marge_nette") or -999))),
       "rejetes": [{k: c.get(k) for k in ("titre", "prix_annonce", "lien", "source", "domaine", "rejet")} for c in cands if c.get("rejet")],
       "duree_s": round(time.monotonic() - DEBUT)}
json.dump(res, open("data/chaine.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

FEU = {"vert": "🟢", "orange": "🟠", "rouge": "🔴"}
FOND = {"Idéfix": "#dbeafe", "Amigo": "#fef3c7"}


def eur(v):
    return f"{v:.2f} €".replace(".", ",") if isinstance(v, (int, float)) else "—"


lignes = ""
for c in res["affaires"]:
    v = c["verdict"]
    if v["feu"] == "rouge":
        continue
    lignes += (f"<tr style='background:{FOND[c['denicheur']]}'><td>{FEU[v['feu']]}{' ⭐' if c['etoile'] else ''}<br><b>{c['denicheur']}</b></td>"
               f"<td>{H.escape((c.get('titre_fiche') or c.get('titre') or '')[:110])}<br><small>EAN {c['ean']}</small></td>"
               f"<td><a href='{H.escape(c.get('lien_marchand') or '#')}'><b>{eur(v.get('achat'))}</b><br>{H.escape(c.get('domaine') or c.get('marchand') or '')}</a></td>"
               f"<td>{eur(v.get('ref_min'))}<br><small>{H.escape(str(v.get('ref_ou') or ''))} · médiane {eur(v.get('ref_mediane'))}</small></td>"
               f"<td>{v.get('ecart_pct', '—')} %</td><td>{v.get('nb_vendeurs', '—')}</td><td>{v.get('ventes_30j') or '—'}</td>"
               f"<td>{eur(v.get('prix_vente'))}</td><td><b>{eur(v.get('marge_nette'))}</b></td>"
               f"<td><small>{H.escape(' ; '.join(v.get('manque') or []) or 'tout est confirmé')}{('<br>' + H.escape(c['note_prix'])) if c.get('note_prix') else ''}</small></td></tr>")
page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chaîne EAN</title>
<style>body{{font-family:system-ui;margin:12px;background:#fff;color:#111}}table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #bbb;padding:5px 7px;vertical-align:top}}th{{background:#eee}}</style>
<h2>Chaîne EAN — {heure}</h2>
<p><span style="background:#dbeafe;padding:2px 8px">Bleu = Idéfix (promo → demande)</span> <span style="background:#fef3c7;padding:2px 8px">Jaune = Amigo (demande → promo)</span>
 · 🟢 bingo · 🟠 à confirmer · ⭐ trouvé par les deux dénicheurs. Les rouges ne sont pas affichés.</p>
<table><tr><th>Feu</th><th>Produit (identifié par code)</th><th>Achat confirmé</th><th>Moins cher ailleurs en France</th><th>Écart</th><th>Marchands</th><th>Ventes Amazon 30 j</th><th>Revente</th><th>Marge nette</th><th>Reste à confirmer</th></tr>{lignes}</table>
<h3>Entonnoir</h3><ul>{''.join(f'<li>{H.escape(k)} : <b>{n}</b></li>' for k, n in ent.items())}</ul></html>"""
open("data/chaine.html", "w", encoding="utf-8").write(page)

print("\nENTONNOIR")
for k, n in ent.items():
    print(f"  {n:4d}  {k}")
print("REJETS (identification)", dict(rejets.most_common(12)))
print("ROUGES (raisons)", dict(raisons_rouges.most_common(8)))
print("MARCHANDS", {d: tuple(v) for d, v in list(sorted(par_dom.items(), key=lambda kv: -kv[1][0]))[:25]})
for c in res["affaires"]:
    v = c["verdict"]
    if v["feu"] != "rouge":
        print(f"{v['feu'].upper():6s} {c['denicheur']:6s} {eur(v.get('achat')):>10s} vs {eur(v.get('ref_min')):>10s} ({v.get('ref_ou')}) "
              f"écart {v.get('ecart_pct')} % marge {eur(v.get('marge_nette'))} | {(c.get('titre_fiche') or c.get('titre') or '')[:60]} | {c.get('lien_marchand')}")
print("durée", res["duree_s"], "s")
