"""RAPPORT POUR DAVID : une seule page HTML, à onglets, avec tri et filtres, qui marche sans serveur (téléphone ou PC).
Onglets : Affaires du passage · Alertes Idéfix (24 h) · Radar Keepa · Hype étrangère · Bingo · Les plus recherchés · Outils.
Chaque ligne est SIGNÉE par le dénicheur qui l'a trouvée (Idéfix, Amigo, Chasseur, Radar Keepa).
-> data/rapport_david.html      python saas/rapport_david.py"""
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARIS = ZoneInfo("Europe/Paris")
TAUX_HYPE, PORT_HYPE, IMPORT_HYPE = {"US": 0.90, "JP": 0.0058}, {"US": 15, "JP": 12}, 1.25   # mêmes valeurs que denicheur/hype_jour.py
PORT_UE, FRAIS_VENTE = 7.0, 0.12


def lire(rel, defaut):
    try:
        return json.load(open(os.path.join(RACINE, rel), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaut


def signe(source, denicheur=None):
    s = (source or "").lower()
    if denicheur == "C" or s == "chasse_ciblee":
        return "Chasseur"
    if s.startswith("keepa"):
        return "Radar Keepa"
    if denicheur == "B" or s.startswith("amigo") or s.startswith("bingo") or s.startswith("hype"):
        return "Amigo"
    return "Idéfix"


def iso_paris(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PARIS).strftime("%d/%m %H:%M")
    except (TypeError, ValueError, AttributeError):
        return ""


def mots(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return set(m for m in re.findall(r"[a-z0-9]+", t) if len(m) > 1)


def construire():
    p = lire("data/dernier_passage.json", {})
    audits = sorted(os.listdir(os.path.join(RACINE, "data/audits"))) if os.path.isdir(os.path.join(RACINE, "data/audits")) else []
    audit = lire(f"data/audits/{audits[-1]}", {}) if audits and audits[-1].startswith(p.get("horodatage", "x")) else {}
    verdicts = {v["id"]: v for v in audit.get("verdicts", [])}
    il_y_a_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="minutes")

    # --- 1. affaires du passage (toutes, avec le verdict de l'audit)
    affaires = []
    for c in p.get("candidats", []):
        v = verdicts.get(c["id"], {})
        verd = v.get("verdict") or c.get("feu") or ("passe" if c.get("passe_verif") else "attente")
        feu = {"valide": "vert", "bon": "orange", "passe": "orange", "rejete": "rouge", "attente": "gris", "vert": "vert", "orange": "orange", "rouge": "rouge"}[verd]
        k = c.get("keepa") or {}
        affaires.append({
            "titre": c.get("nom_produit") or c.get("titre"), "titre_complet": c.get("titre"), "prix": c.get("prix"), "cout": c.get("cout_achat"),
            "marchand": c.get("marchand"), "pays": c.get("pays"), "lien": c.get("lien"), "denicheur": signe(c.get("source")),
            "source": c.get("source"), "feu": feu, "verdict": verd,
            "neuf_min": (c.get("prix_plancher") or {}).get("prix_min") or (c.get("verification") or {}).get("prix_neuf_min"),
            "neuf_ou": (c.get("prix_plancher") or {}).get("ou") or (c.get("verification") or {}).get("marchand_neuf_min"),
            "occ_bas": (c.get("occasion") or {}).get("bas") or (c.get("verification") or {}).get("occasion_bas"),
            "occ_haut": (c.get("occasion") or {}).get("haut") or (c.get("verification") or {}).get("occasion_haut"),
            "vendeurs": c.get("vendeurs_amazon"), "concurrence": c.get("concurrence_amazon"),
            "revente": v.get("prix_revente_verifie") or c.get("prix_revente_prudent"), "marge": v.get("marge_nette_verifiee") if v.get("marge_nette_verifiee") is not None else c.get("marge_verifiee"),
            "canal": v.get("ou_vendre") or c.get("plateforme_revente"), "ean": c.get("ean"), "ventes30": k.get("ventes_estimees_30j"),
            "volume_google": (c.get("demande_google") or {}).get("volume_mensuel"), "bingo": bool(c.get("bingo")), "annonces_ebay": c.get("annonces_ebay"), "mot_cle": c.get("mot_cle"), "score_vente": c.get("score_vente"),
            "date": p.get("horodatage", "").replace("_", " ")[:16], "motif": v.get("commentaire") or (c.get("verification") or {}).get("remarque") or "",
        })

    # --- 2. alertes Idéfix des 24 dernières heures
    alertes = []
    for a in lire("data/alertes.json", []):
        if (a.get("trouve_le") or "") < il_y_a_24h:
            continue
        v = a.get("verdict") or {}
        st = a.get("statut")
        feu = {"valide": "vert", "bon": "orange", "bon_plan": "orange", "a_verifier": "gris"}.get(st, "rouge")
        meilleur = max((x for x in (a.get("canaux") or []) if isinstance(x, dict)), key=lambda x: x.get("marge_nette") or 0, default={})
        alertes.append({
            "titre": a.get("nom_produit") or a.get("titre"), "titre_complet": a.get("titre"), "prix": a.get("prix"), "cout": a.get("cout_achat"),
            "marchand": a.get("marchand"), "pays": a.get("pays"), "lien": a.get("lien"), "denicheur": signe(a.get("source"), a.get("denicheur")),
            "source": a.get("source"), "feu": feu, "verdict": st, "economie": a.get("economie_pct"),
            "neuf_min": (a.get("idealo") or {}).get("prix_min") or (a.get("prix_plancher") or {}).get("prix_min"),
            "neuf_ou": "idealo" if a.get("idealo") else (a.get("prix_plancher") or {}).get("ou"),
            "occ_bas": min((x.get("min") for x in (a.get("revente_reelle") or {}).values() if isinstance(x, dict) and x.get("min")), default=None),
            "revente": v.get("prix_revente_verifie") or meilleur.get("prix_vente"), "marge": v.get("marge_nette_verifiee") if v.get("marge_nette_verifiee") is not None else meilleur.get("marge_nette"),
            "canal": v.get("canal") or meilleur.get("canal"), "date": iso_paris(a.get("trouve_le")), "date_iso": a.get("trouve_le"),
            "motif": v.get("commentaire") or "", "duree": v.get("duree_offre"),
        })
    alertes.sort(key=lambda x: x.get("date_iso") or "", reverse=True)

    # --- 3. radar, 4. hype, 5. bingo, 6. demande
    radar = lire("data/radar_amazon.json", {})
    hype = lire("data/hype_etranger.json", {})
    bingo = lire("data/bingo.json", {})
    dem = lire("data/demande.json", {})
    recents = lire("data/etat/annonces_recentes.json", [])
    px = lire("data/recherches_prix.json", {})
    prix_q = px.get("recherches") or {}
    par_q, rangs = {}, {}
    for x in dem.get("liste", []):
        q = (x.get("recherche") or "").strip()
        if not q:
            continue
        pays = x.get("pays")
        rangs[pays] = rangs.get(pays, 0) + 1
        r = par_q.setdefault(q.lower(), {"recherche": q, "pays": {}, "hausse": None, "nouveau": False, "top10": False})
        r["pays"][pays] = x.get("popularite")
        r["hausse"] = max(r["hausse"] or 0, x.get("hausse_pct") or 0)
        r["nouveau"] = r["nouveau"] or bool(x.get("nouveau"))
    for pays in rangs:
        for r in sorted([r for r in par_q.values() if pays in r["pays"]], key=lambda r: -(r["pays"][pays] or 0))[:10]:
            r["top10"] = True
    demande = []
    for k, r in par_q.items():
        r["popularite"] = max((v or 0) for v in r["pays"].values())
        r["pays_top"] = max(r["pays"], key=lambda p: r["pays"][p] or 0)
        q = mots(r["recherche"])
        vues = [a for a in recents if q and q <= mots(a.get("titre"))]
        r["vues"] = [{"prix": a.get("prix"), "titre": a.get("titre"), "lien": a.get("lien")} for a in vues[:3]]
        r["nb_vues"] = len(vues)
        i = prix_q.get(k) or {}
        if i.get("nb"):
            r.update({"moins_cher": i["moins_cher"], "plus_cher": i["plus_cher"], "meilleure_vente": i["meilleure_vente"], "par_pays": i.get("par_pays"),
                      "prix_min": i["moins_cher"]["prix"], "prix_max": i["plus_cher"]["prix"], "ventes": i["meilleure_vente"].get("ventes_30j")})
        demande.append(r)

    # --- hype : tarifs (là-bas, Amazon Europe, coût rendu, revente mini pour gagner 20 €)
    prix_h = px.get("hype") or {}
    index_k = lire("data/base/keepa_index.json", {})
    hype_l = []
    for x in hype.get("produits", []):
        pl = x.get("prix_labas")
        pays = x.get("pays")
        pe = round((pl * 100 if pays == "JP" else pl) * TAUX_HYPE.get(pays, 1), 2) if isinstance(pl, (int, float)) else None
        europe = {k: v for k, v in (prix_h.get(x.get("asin")) or {}).items() if k in ("DE", "IT", "ES") and v}
        couts = ([round((pe + PORT_HYPE.get(pays, 15)) * IMPORT_HYPE, 2)] if pe else []) + [round(v + PORT_UE, 2) for v in europe.values()]
        cout = min(couts) if couts else None
        m90_fr = (index_k.get(f'{x.get("asin")}:FR') or {}).get("m90")
        ref_fr = min(v for v in (x.get("prix_fr"), m90_fr or x.get("prix_fr")) if v) if x.get("prix_fr") else None
        hype_l.append({**x, "prix_eur": pe, "europe": europe, "europe_min": min(europe.values()) if europe else None, "cout_rendu": cout,
                       "prix_mini": round((cout + 20) / (1 - FRAIS_VENTE), 2) if cout and not x.get("prix_fr") else None,
                       "benefice": round(ref_fr * 0.95 * (1 - FRAIS_VENTE) - cout, 2) if cout and ref_fr else None,   # même calcul que denicheur/hype_jour.py
                       # prix français peu crédible : presque aucune vente en France, ou prix très au-dessus du prix d'origine
                       "prix_fr_douteux": bool(ref_fr and pe and ((x.get("rang_fr") or 0) > 300000 or ref_fr > 2 * pe)),
                       "lien_labas": f"https://www.amazon.{'co.jp' if pays == 'JP' else 'com'}/dp/{x.get('asin')}"})

    # --- 7. outils (consommation)
    apify, dfs, keepa, moisson = lire("data/etat/apify_budget.json", {}), lire("data/etat/dataforseo_budget.json", {}), lire("data/etat/keepa_budget.json", {}), lire("data/etat/moisson.json", {})
    outils = [
        {"outil": "Apify (idealo, Leboncoin, Vinted)", "mois": f"{apify.get('depense_reelle_usd', 0):.2f} $ réels / {apify.get('depense_estimee_usd', 0):.2f} $ estimés", "plafond": "35 $/mois", "appels": apify.get("appels")},
        {"outil": "DataForSEO (volumes Google, Trends)", "mois": f"{dfs.get('depense_mois_usd', 0):.2f} $ (aujourd'hui {dfs.get('depense_usd', 0):.2f} $)", "plafond": "0,70 $/jour · dépôt 50 $", "appels": dfs.get("appels")},
        {"outil": "Keepa (fiches + moissonneur)", "mois": f"{moisson.get('jetons_jour', 0)} jetons aujourd'hui, {moisson.get('tours', 0)} récoltes, base {len(lire('data/base/keepa_index.json', {}))} fiches", "plafond": "28 800 jetons/jour (abonnement)", "appels": keepa.get("appels")},
        {"outil": "Gemini (vérification Google)", "mois": f"{(p.get('verification') or {}).get('faits', 0)} vérifications au dernier passage", "plafond": "20 €/mois", "appels": None},
        {"outil": "Tribunal (IA gratuites)", "mois": ", ".join(f"{k} {v['reussites']}/{v['appels'] if v['appels'] < 10**6 else 'coupé'}" for k, v in (p.get("agents") or {}).items()), "plafond": "quotas gratuits", "appels": None},
    ]

    dp = lire("data/demande_pays.json", {})
    arb = lire("data/arbitrage.json", {})
    audits_arb = lire("data/arbitrage_audit.json", {})
    ecarts = []
    for x in arb.get("ecarts", []):
        ref = min(v for v in (x.get("prix_fr"), x.get("moyenne_90j_fr") or x.get("prix_fr")) if v)
        a = audits_arb.get(x.get("asin"))
        ecarts.append({**x, "ecart_reel": round((1 - x["cout_rendu"] / ref) * 100), "marge_estimee": round(ref * 0.85 - x["cout_rendu"], 2),
                       "douteux": bool(x["prix_fr"] > 1.25 * (x.get("moyenne_90j_fr") or x["prix_fr"]) or (x.get("moyenne_90j_fr") or 0) > 1.25 * x["prix_fr"] or x.get("vendeurs_fr") == 1),
                       "audit": a, "verdict": (a or {}).get("verdict")})
    srcg = lire("data/sourcing.json", {})
    chs = lire("data/pc/chasse.json", {})
    donnees = {"chasse": chs.get("annonces", [])[:300], "chasse_maj": iso_paris(chs.get("maj")), "chasse_etat": chs.get("etat", {}),"sourcing": list((srcg.get("fiches") or {}).values())[::-1][:40], "sourcing_maj": iso_paris(srcg.get("maj")),"arbitrage": ecarts, "arbitrage_maj": iso_paris(arb.get("maj")), "arbitrage_total": arb.get("compares_total", 0),"demande_pays": dp.get("pays", {}), "demande_pays_maj": iso_paris(dp.get("maj")), "genere": datetime.now(PARIS).strftime("%d/%m/%Y %H:%M"), "passage": p.get("date_affichee"), "resume_audit": audit.get("resume"),
               "affaires": affaires, "alertes": alertes, "radar": radar.get("affaires", [])[:300], "radar_maj": iso_paris(radar.get("maj")),
               "hype": hype_l, "hype_prix_maj": iso_paris(px.get("maj")), "prix_recherches_maj": iso_paris(px.get("maj")), "hype_maj": iso_paris(hype.get("maj")), "bingo": bingo.get("bingos", []), "bingo_maj": iso_paris(bingo.get("maj")),
               "bingo_info": f"{bingo.get('nb_candidats', 0)} candidats, {bingo.get('nb_avec_volume', 0)} avec volume Google" if bingo else "pas encore calculé",
               "vagues": bingo.get("vagues", []), "demande": demande, "demande_maj": iso_paris(dem.get("maj")), "outils": outils}

    page = PAGE.replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/"))
    with open(os.path.join(RACINE, "data/rapport_david.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"data/rapport_david.html : {len(affaires)} affaires, {len(alertes)} alertes 24 h, {len(donnees['radar'])} radar, {len(donnees['hype'])} hype, {len(donnees['bingo'])} bingo")


PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dénicheur — rapport</title>
<style>
:root{--vert:#1a7f37;--orange:#b35900;--rouge:#b3261e;--gris:#777}
body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2937;color:#fff;padding:12px 14px}header h1{margin:0;font-size:1.15em}header .note{color:#cbd5e1;font-size:.85em;margin-top:4px}
nav{display:flex;flex-wrap:wrap;gap:6px;padding:8px 10px;background:#fff;border-bottom:1px solid #ddd;position:sticky;top:0;z-index:5}
nav button{border:1px solid #cbd5e1;background:#f8fafc;border-radius:16px;padding:6px 11px;cursor:pointer;font-size:.9em}
nav button.actif{background:#1f2937;color:#fff;border-color:#1f2937}
.barre{display:flex;flex-wrap:wrap;gap:6px;padding:8px 10px;align-items:center;font-size:.9em}
.barre select,.barre input{padding:5px 7px;border:1px solid #cbd5e1;border-radius:6px;font-size:.95em}
section{display:none;padding:0 10px 30px}section.actif{display:block}
.carte{background:#fff;border:1px solid #e5e7eb;border-left:6px solid var(--gris);border-radius:8px;padding:10px 12px;margin:8px 0}
.carte.vert{border-left-color:var(--vert)}.carte.orange{border-left-color:var(--orange)}.carte.rouge{border-left-color:var(--rouge)}
.carte h3{margin:0 0 4px;font-size:1em}.carte a{color:#0b57d0;text-decoration:none}.carte .ligne{font-size:.9em;color:#444;margin:2px 0}
.badge{display:inline-block;font-size:.75em;padding:2px 7px;border-radius:10px;background:#e5e7eb;margin-right:4px}
.badge.den{background:#dbeafe}.badge.vert{background:#dcfce7;color:var(--vert)}.badge.orange{background:#ffedd5;color:var(--orange)}.badge.rouge{background:#fee2e2;color:var(--rouge)}
.marge{font-weight:700}.marge.pos{color:var(--vert)}.marge.neg{color:var(--rouge)}.motif{font-size:.85em;color:#555;margin-top:4px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:.88em}th,td{border:1px solid #e5e7eb;padding:5px 7px;text-align:left;vertical-align:top}th{background:#f1f5f9}
.vide{padding:14px;background:#fff7e0;border:1px solid #f0d58c;border-radius:8px;margin:8px 0}
.compte{font-size:.85em;color:#666;padding:0 10px}
.tribar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:8px 0;background:#f5f6f8;position:sticky;top:var(--nav,44px);z-index:4;font-size:.9em}
.tribar .lib{font-weight:600}.tribar button{border:1px solid #cbd5e1;background:#fff;border-radius:14px;padding:6px 10px;cursor:pointer;font-size:.95em}
.tribar button.actif{background:#0b57d0;color:#fff;border-color:#0b57d0}.tribar button.puce.actif{background:var(--orange);border-color:var(--orange)}
.tribar select,.tribar input{padding:5px 7px;border:1px solid #cbd5e1;border-radius:6px;font-size:.95em;max-width:170px}.tribar input{flex:1;min-width:120px}
.defil{overflow-x:auto}th.triable{cursor:pointer;white-space:nowrap}th.triable:hover{background:#e2e8f0}td a{color:#0b57d0;text-decoration:none}
.carte.gris{border-left-color:var(--gris)}
@media(max-width:700px){nav{flex-wrap:nowrap;overflow-x:auto}nav button{white-space:nowrap;flex:none}.tribar{flex-wrap:nowrap;overflow-x:auto}.tribar button,.tribar label{white-space:nowrap;flex:none}.tribar input{min-width:130px}}
</style></head><body>
<header><h1>Le Dénicheur — rapport</h1><div class="note" id="entete"></div></header>
<nav id="nav"></nav>
<div class="barre" id="barre">
  <label>Trier <select id="tri"><option value="pertinence">pertinence</option><option value="score_vente">score de vente</option><option value="prix_asc">prix croissant</option><option value="prix_desc">prix décroissant</option><option value="marge">marge</option><option value="economie">% d'économie</option><option value="date">plus récent</option></select></label>
  <label>Feu <select id="feu"><option value="">tous</option><option value="vert">vert</option><option value="orange">orange</option><option value="rouge">rouge</option><option value="gris">à vérifier</option></select></label>
  <label>Dénicheur <select id="den"><option value="">tous</option><option>Idéfix</option><option>Amigo</option><option>Chasseur</option><option>Radar Keepa</option></select></label>
  <label>Pays <select id="pays"><option value="">tous</option></select></label>
  <label>Prix max <input id="pmax" type="number" style="width:80px" placeholder="€"></label>
  <input id="q" type="search" placeholder="rechercher…" style="flex:1;min-width:140px">
</div>
<div class="compte" id="compte"></div>
<section id="s_affaires"></section><section id="s_alertes"></section><section id="s_radar"></section><section id="s_hype"></section>
<section id="s_bingo"></section><section id="s_demande"></section><section id="s_arbitrage"></section><section id="s_sourceur"></section><section id="s_chasseur"></section><section id="s_pays"></section><section id="s_outils"></section>
<script>
const D = __DONNEES__;
const ONGLETS=[["affaires","Affaires du passage"],["alertes","Alertes Idéfix 24 h"],["radar","Radar Keepa"],["hype","Hype étrangère"],["bingo","Bingo"],["demande","Les plus recherchés"],["arbitrage","Arbitrage Europe"],["sourceur","Sourceur (bingos)"],["chasseur","Chasseur (particuliers)"],["pays","Demande par pays"],["outils","Outils"]];
const e=t=>String(t??"—").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const eur=v=>typeof v==="number"?v.toFixed(2).replace(".",",")+" €":"—";
let actif="affaires";
document.getElementById("entete").textContent=`Généré le ${D.genere} · dernier passage : ${D.passage||"—"}`+(D.resume_audit?` · Audit : ${D.resume_audit}`:"");
const nav=document.getElementById("nav");
ONGLETS.forEach(([k,n])=>{const b=document.createElement("button");const nb=k==="affaires"?D.affaires.length:k==="alertes"?D.alertes.length:k==="radar"?D.radar.length:k==="hype"?D.hype.length:k==="bingo"?D.bingo.length:k==="demande"?D.demande.length:k==="arbitrage"?(D.arbitrage||[]).length:"";b.textContent=n+(nb!==""?` (${nb})`:"");b.onclick=()=>{actif=k;rendre()};b.dataset.k=k;nav.appendChild(b)});
const paysSel=document.getElementById("pays");[...new Set([...D.affaires,...D.alertes].map(x=>x.pays).filter(Boolean))].sort().forEach(p=>{const o=document.createElement("option");o.textContent=p;paysSel.appendChild(o)});
["tri","feu","den","pays","pmax","q"].forEach(id=>document.getElementById(id).addEventListener("input",rendre));
function filtre(liste){const f=document.getElementById("feu").value,d=document.getElementById("den").value,p=document.getElementById("pays").value,pm=parseFloat(document.getElementById("pmax").value),q=document.getElementById("q").value.toLowerCase();
 return liste.filter(x=>(!f||x.feu===f)&&(!d||x.denicheur===d)&&(!p||x.pays===p)&&(isNaN(pm)||(x.prix??0)<=pm)&&(!q||JSON.stringify(x).toLowerCase().includes(q)));}
function trier(liste){const t=document.getElementById("tri").value;const c=[...liste];
 if(t==="score_vente")c.sort((a,b)=>(b.score_vente??-1)-(a.score_vente??-1));else if(t==="prix_asc")c.sort((a,b)=>(a.prix??1e9)-(b.prix??1e9));else if(t==="prix_desc")c.sort((a,b)=>(b.prix??-1)-(a.prix??-1));
 else if(t==="marge")c.sort((a,b)=>(b.marge??-1e9)-(a.marge??-1e9));else if(t==="economie")c.sort((a,b)=>(b.economie??b.baisse_pct??-1)-(a.economie??a.baisse_pct??-1));
 else if(t==="date")c.sort((a,b)=>String(b.date_iso||b.vu||b.date||"").localeCompare(String(a.date_iso||a.vu||a.date||"")));
 else c.sort((a,b)=>({vert:0,orange:1,gris:2,rouge:3}[a.feu]??2)-({vert:0,orange:1,gris:2,rouge:3}[b.feu]??2)||(b.marge??-1e9)-(a.marge??-1e9));return c;}
function carte(x){const m=x.marge;const cm=typeof m==="number"?`<span class="marge ${m>=8?"pos":m<0?"neg":""}">${m>=0?"+":""}${m.toFixed(2).replace(".",",")} €</span>`:"—";
 return `<div class="carte ${x.feu}"><h3><span class="badge ${x.feu}">${e(x.verdict)}</span><span class="badge den">${e(x.denicheur)}</span>${x.bingo?'<span class="badge orange">BINGO</span>':""}<a href="${e(x.lien)}" target="_blank">${e(x.titre)}</a></h3>
 <div class="ligne"><b>${eur(x.prix)}</b> chez ${e(x.marchand)} (${e(x.pays)})${x.cout?` · coût rendu ${eur(x.cout)}`:""}${x.economie?` · <b>-${x.economie} %</b> vs neuf`:""}</div>
 <div class="ligne">Neuf le moins cher : ${eur(x.neuf_min)}${x.neuf_ou?` (${e(x.neuf_ou)})`:""} · Occasion : ${x.occ_bas||x.occ_haut?`${eur(x.occ_bas)} → ${eur(x.occ_haut)}`:"—"} · Revente retenue : ${eur(x.revente)} sur ${e(x.canal)} · Marge : ${cm}</div>
 <div class="ligne">${x.vendeurs!=null?`vendeurs Amazon : ${x.vendeurs} (concurrence ${e(x.concurrence)}) · `:""}${x.ean?`EAN ${e(x.ean)} · `:""}${x.ventes30!=null?`ventes Amazon 30 j : ${x.ventes30} · `:""}${x.volume_google?`recherches Google : ${x.volume_google}/mois (« ${e(x.mot_cle)} ») · `:""}${x.annonces_ebay!=null?`annonces eBay neuves : ${x.annonces_ebay} · `:""}${x.score_vente!=null?`score de vente : <b>${x.score_vente}</b> · `:""}${x.duree?`durée : ${e(x.duree)} · `:""}${e(x.date)} · source ${e(x.source)}</div>
 ${x.motif?`<div class="motif">${e(x.motif)}</div>`:""}</div>`;}
/* Tableaux triables : une barre de boutons, des filtres, une recherche, et l'en-tête cliquable. */
const CFG={},ET={};
const amz=(p,a)=>`https://www.amazon.${{FR:"fr",DE:"de",IT:"it",ES:"es",US:"com",JP:"co.jp"}[p]||"fr"}/dp/${a}`;
const mg=m=>typeof m==="number"?`<span class="marge ${m>=8?"pos":m<0?"neg":""}">${m>=0?"+":""}${m.toFixed(2).replace(".",",")} €</span>`:"—";
function liens(t,ean,p){const q=encodeURIComponent(ean||String(t||"").slice(0,70)),n=encodeURIComponent(String(t||"").split(/[,(|]/)[0].slice(0,60));const d={FR:"fr",DE:"de",IT:"it",ES:"es"}[p]||"fr";
 return [[`https://www.idealo.${d}/prechcat.html?q=${q}`,"idealo"],[`https://www.google.fr/search?tbm=shop&q=${q}`,"Google"],[`https://www.leboncoin.fr/recherche?text=${n}`,"Leboncoin"],[`https://www.vinted.fr/catalog?search_text=${n}`,"Vinted"]].map(([u,l])=>`<a href="${e(u)}" target="_blank">${l}</a>`).join(" · ");}
function cadre(o,c){CFG[o]=c;const s=ET[o]=ET[o]||{cle:c.tri,sens:(c.tris.find(t=>t[1]===c.tri)||[0,0,-1])[2],q:"",f:{},p:{}};
 const opts=k=>[...new Set(c.lignes.map(x=>x[k]).filter(v=>v!=null&&v!==""))].sort((a,b)=>String(a).localeCompare(String(b),"fr"));
 return `<div class="tribar"><span class="lib">Trier :</span>${c.tris.map(([l,k])=>`<button data-tri="${k}" onclick="choisir('${o}','${k}')">${l}</button>`).join("")}${(c.puces||[]).map(([l],i)=>`<button class="puce" data-p="${i}" onclick="puce('${o}',${i})">${l}</button>`).join("")}${(c.filtres||[]).map(([l,k])=>`<label>${l} <select onchange="filtrer('${o}','${k}',this.value)"><option value="">tous</option>${opts(k).map(v=>`<option${s.f[k]===String(v)?" selected":""}>${e(v)}</option>`).join("")}</select></label>`).join("")}<input type="search" placeholder="rechercher…" value="${e(s.q).replace("—","")}" oninput="chercher('${o}',this.value)"></div><div class="compte" id="n_${o}"></div><div class="defil" id="t_${o}"></div>`;}
function choisir(o,k){const s=ET[o],c=CFG[o];if(s.cle===k)s.sens=-s.sens;else{s.cle=k;const t=c.tris.find(t=>t[1]===k);s.sens=t?t[2]:-1;}majTable(o);}
function puce(o,i){ET[o].p[i]=!ET[o].p[i];majTable(o);}
function filtrer(o,k,v){ET[o].f[k]=v;majTable(o);}
function chercher(o,v){ET[o].q=v.toLowerCase();majTable(o);}
function majTable(o){const c=CFG[o],s=ET[o],zone=document.getElementById("t_"+o);if(!zone)return;
 let l=c.lignes.filter(x=>Object.entries(s.f).every(([k,v])=>!v||String(x[k])===v)&&Object.entries(s.p).every(([i,a])=>!a||c.puces[i][1](x))&&(!s.q||JSON.stringify(x).toLowerCase().includes(s.q)));
 const col=(c.cols||[]).find(k=>k.k===s.cle),v=x=>col&&col.v?col.v(x):x[s.cle];
 l=[...l].sort((a,b)=>{const m=v(a),n=v(b);if(m==null||m==="")return 1;if(n==null||n==="")return -1;return (typeof m==="number"&&typeof n==="number"?m-n:String(m).localeCompare(String(n),"fr"))*s.sens;});
 zone.innerHTML=c.rendu?l.map(c.rendu).join(""):`<table><tr>${c.cols.map(k=>k.tri===false?`<th>${k.t}</th>`:`<th class="triable" onclick="choisir('${o}','${k.k}')">${k.t}${s.cle===k.k?(s.sens>0?" ▲":" ▼"):""}</th>`).join("")}</tr>${l.map(x=>`<tr>${c.cols.map(k=>`<td>${k.h?k.h(x):e(x[k.k])}</td>`).join("")}</tr>`).join("")}</table>`;
 document.getElementById("n_"+o).textContent=`${l.length} ligne(s) sur ${c.lignes.length}`;
 const bar=zone.parentNode.querySelector(".tribar");bar.querySelectorAll("button[data-tri]").forEach(b=>{const on=b.dataset.tri===s.cle;b.classList.toggle("actif",on);b.textContent=b.textContent.replace(/ [▲▼]$/,"")+(on?(s.sens>0?" ▲":" ▼"):"");});bar.querySelectorAll("button[data-p]").forEach(b=>b.classList.toggle("actif",!!s.p[b.dataset.p]));}
function carteArb(x){const a=x.audit||{};return `<div class="carte ${a.verdict==="à tester"?"orange":a.verdict?"rouge":"gris"}"><h3><span class="badge den">Amigo</span><span class="badge ${a.verdict==="à tester"?"orange":a.verdict?"rouge":""}">${e(a.verdict||"à auditer")}</span><b>-${e(x.ecart_pct)} %</b> <a href="${e(x.lien_fr)}" target="_blank">${e(x.titre)}</a></h3>
 <div class="ligne"><a href="${e(x.lien_achat)}" target="_blank"><b>${eur(x.prix_achat)} sur Amazon ${e(x.pays_achat)}</b></a> · rendu France ${eur(x.cout_rendu)} · <a href="${e(x.lien_fr)}" target="_blank">Amazon.fr ${eur(x.prix_fr)}</a> · moyenne 90 j ${eur(x.moyenne_90j_fr)} · écart réel ${x.ecart_reel!=null?`-${e(x.ecart_reel)} %`:"—"} · marge estimée ${mg(x.marge_estimee)}</div>
 <div class="ligne">${e(x.marque)} · EAN ${e(x.ean)} · ASIN ${e(x.asin)} · ${e(x.ventes_30j_fr)} ventes/mois · ${e(x.vendeurs_fr)} vendeur(s) FR · rang ${e(x.rang_fr)} · vu le ${e((x.vu||"").slice(5,16).replace("T"," "))}</div>
 ${a.neuf_fr?`<div class="ligne">Prix neuf de référence : <b>${eur(a.neuf_fr)}</b> (${e(a.neuf_ou)}) · revente retenue ${eur(a.revente)} · marge ${mg(a.marge)}</div>`:""}
 <div class="ligne">${liens(x.titre,x.ean)}</div>${a.commentaire?`<div class="motif">${e(a.commentaire)}</div>`:`<div class="motif">Pas encore audité : vérifié au prochain passage.</div>`}</div>`;}
function carteSource(x){const li=(arr,f)=>arr&&arr.length?"<ul>"+arr.map(f).join("")+"</ul>":"<i>aucun trouvé</i>";
 return `<div class="carte ${x.type==="produit_usine"?"vert":x.type==="mixte"?"orange":"gris"}"><h3><span class="badge den">Sourceur</span><span class="badge">${e(x.type)}</span>${e(x.titre||x.mot_cle)}</h3>
   <div class="ligne">Recherches ${e(x.recherches_mois)}/mois · vendeurs Amazon ${e(x.vendeurs)} · prix FR ${eur(x.prix_fr)} · fabricant <b>${e(x.fabricant)}</b> (${e(x.pays_fabrication)}) · prix d'achat cible <b>${eur(x.prix_achat_cible_eur)}</b> · marge possible ${e(x.marge_possible_pct)} %</div>
   <div class="ligne"><b>Meilleure piste :</b> ${e(x.meilleure_piste)}</div>
   ${x.vendeurs_amazon&&x.vendeurs_amazon.length?`<div class="ligne"><b>Qui vend le moins cher sur Amazon.fr :</b> ${x.vendeurs_amazon.map(v=>`${e(v.vendeur||v.sellerId)} (${e(v.societe||"?")}, ${e(v.pays||"?")}) ${eur(v.prix)}`).join(" · ")}</div>`:""}
   ${x.comment_font_les_vendeurs?`<div class="ligne"><b>Comment font-ils :</b> ${e(x.comment_font_les_vendeurs)}</div>`:""}
   <div class="ligne"><b>Distributeurs officiels :</b> ${li(x.distributeurs_officiels,d=>`<li>${e(d.nom)} (${e(d.pays)}) — ${d.site?`<a href="${e(d.site)}" target="_blank">${e(d.site)}</a>`:""} · ${e(d.comment_contacter)} · ${e(d.conditions)}</li>`)}</div>
   <div class="ligne"><b>Grossistes :</b> ${li(x.grossistes,g=>`<li>${e(g.nom)} — ${g.site?`<a href="${e(g.site)}" target="_blank">${e(g.site)}</a>`:""} · ${e(g.prix_ou_remise)} · minimum ${e(g.minimum)} · ${e(g.note)}</li>`)}</div>
   <div class="ligne"><b>Usines / fournisseurs :</b> ${li(x.usines_ou_fournisseurs,u=>`<li>${e(u.nom)} (${e(u.plateforme)}) — ${u.lien?`<a href="${e(u.lien)}" target="_blank">lien</a>`:""} · ${eur(u.prix_unitaire_estime_eur)} · minimum ${e(u.quantite_minimum)} · ${e(u.delai_jours)} j · ${e(u.note)}</li>`)}</div>
   <div class="ligne"><b>Risques :</b> ${e((x.risques||[]).join(", "))}</div>
   <div class="motif"><b>Message de négociation :</b><br>${e(x.message_negociation).replace(/\n/g,"<br>")}</div>
   <div class="ligne"><small>Sources : ${(x.sources_google||x.sources||[]).slice(0,6).map(u=>`<a href="${e(u)}" target="_blank">${e(String(u).slice(0,50))}</a>`).join(" · ")}</small></div></div>`;}
function rendre(){document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("actif",b.dataset.k===actif));document.querySelectorAll("section").forEach(s=>s.classList.toggle("actif",s.id==="s_"+actif));
 document.getElementById("barre").style.display=["affaires","alertes","radar"].includes(actif)?"flex":"none";let html="",n=0;
 if(actif==="affaires"){const l=trier(filtre(D.affaires));n=l.length;html=l.length?l.map(carte).join(""):`<div class="vide">Aucune affaire du passage ne correspond aux filtres.</div>`;if(!D.affaires.some(x=>x.feu==="vert"))html=`<div class="vide">Aucune carte verte à ce passage : voici toutes les affaires examinées avec le motif de l'audit. Les alertes Idéfix des 24 h sont dans l'onglet suivant.</div>`+html;}
 else if(actif==="alertes"){const l=trier(filtre(D.alertes));n=l.length;html=l.length?l.map(carte).join(""):`<div class="vide">Aucune alerte sur 24 h avec ces filtres.</div>`;}
 else if(actif==="radar"){const l=trier(filtre(D.radar.map(a=>({...a,feu:"gris",verdict:a.type,denicheur:"Radar Keepa",pays:"FR",marchand:"Amazon.fr",economie:a.baisse_pct,neuf_min:a.moyenne_90j,neuf_ou:"moyenne 90 j Amazon",date:a.vu,date_iso:a.vu,source:"keepa-radar"}))));n=l.length;html=`<div class="vide">Baisses de prix Amazon.fr (mise à jour ${e(D.radar_maj)}) : ce sont des pistes, pas des affaires vérifiées. Chaque baisse entre dans le passage suivant.</div>`+l.map(carte).join("");}
 else if(actif==="hype"){const M=D.hype_prix_maj;html=`<div class="vide">Meilleures ventes Amazon USA / Japon absentes ou mal vendues en France (mise à jour ${e(D.hype_maj)}). « Coût rendu » = achat là-bas, port et taxes d'import compris, ou Amazon Europe + 7 € de port si c'est moins cher. « Bénéfice au prix FR » = ce qu'il reste par pièce en vendant 5 % sous le prix Amazon.fr (ou sa moyenne 90 jours si elle est plus basse), après 12 % de frais : en rouge, c'est une perte. « Prix FR à vérifier » : le produit ne se vend presque pas en France ou son prix dépasse le double du prix d'origine, le bénéfice n'est alors pas fiable. « Revente mini » n'apparaît que pour les produits absents d'Amazon.fr : c'est le prix à atteindre pour gagner 20 €. « Mal vendu » veut dire peu de ventes sur Amazon.fr (au-delà de la 20 000e place), pas un mauvais prix. Prix Europe relevés par Keepa${M?` (${e(M)})`:""}. Trouvé par Amigo.</div>`+cadre("hype",{lignes:D.hype,tri:"ventes_30j_labas",tris:[["Ventes là-bas","ventes_30j_labas",-1],["Rang là-bas","rang_labas",1],["Prix là-bas","prix_eur",1],["Bénéfice au prix FR","benefice",-1],["Coût rendu","cout_rendu",1],["Revente mini","prix_mini",1],["Prix FR","prix_fr",1],["Prix Europe","europe_min",1]],filtres:[["Pays","pays"],["En France","en_france"],["Catégorie","categorie"]],puces:[["Rentables et prix FR fiable",x=>x.benefice>0&&!x.prix_fr_douteux]],
  cols:[{k:"pays",t:"Pays"},{k:"titre",t:"Produit",h:x=>`<a href="${e(x.lien_labas)}" target="_blank">${e((x.titre||"").slice(0,90))}</a>${x.marque?`<br><small>${e(x.marque)}</small>`:""}`},{k:"categorie",t:"Catégorie"},{k:"ventes_30j_labas",t:"Ventes 30 j là-bas",h:x=>`<b>${e(x.ventes_30j_labas)}</b>`},{k:"rang_labas",t:"Rang"},{k:"prix_eur",t:"Prix là-bas",h:x=>eur(x.prix_eur)},{k:"europe_min",t:"Amazon Europe",h:x=>x.europe&&Object.keys(x.europe).length?Object.entries(x.europe).map(([p,v])=>`<a href="${e(amz(p,x.asin))}" target="_blank">${e(p)} ${eur(v)}</a>`).join("<br>"):"—"},{k:"cout_rendu",t:"Coût rendu",h:x=>eur(x.cout_rendu)},{k:"benefice",t:"Bénéfice au prix FR",h:x=>mg(x.benefice)+(x.prix_fr_douteux?'<br><span class="badge rouge">prix FR à vérifier</span>':"")},{k:"prix_mini",t:"Revente mini",h:x=>eur(x.prix_mini)},{k:"en_france",t:"En France",h:x=>`<span class="badge ${x.en_france==="absent"?"vert":"orange"}">${e(x.en_france)}</span>`},{k:"prix_fr",t:"Prix FR",h:x=>x.prix_fr?`<a href="${e(x.lien_fr)}" target="_blank">${eur(x.prix_fr)}</a>`:"—"},{k:"lien_fr",t:"Liens",tri:false,h:x=>liens(x.titre,x.ean)}]});}
 else if(actif==="bingo"){html=`<div class="vide">Bingo = très recherché sur Google France (≥ 1 000/mois) ET peu de vendeurs (≤ 5 sur Amazon, ≤ 15 annonces eBay). ${e(D.bingo_info)} (mise à jour ${e(D.bingo_maj)}). Trouvé par Amigo.</div>`+(D.bingo.length?cadre("bingo",{lignes:D.bingo,tri:"recherches_mois",tris:[["Recherches","recherches_mois",-1],["Moins de vendeurs","vendeurs",1],["Ventes 30 j","ventes_30j",-1],["Prix Amazon","prix",1],["Neuf FR","prix_neuf_france",1],["Score","score",-1]],filtres:[["Origine","origine"]],
  cols:[{k:"mot_cle",t:"Mot-clé",h:x=>`<b>${e(x.mot_cle)}</b><br><small>${e((x.titre||"").slice(0,80))}</small>`},{k:"recherches_mois",t:"Recherches/mois",h:x=>`<b>${e(x.recherches_mois)}</b>`},{k:"vendeurs",t:"Vendeurs Amazon"},{k:"ventes_30j",t:"Ventes 30 j"},{k:"marchands_france",t:"Marchands France (idealo)"},{k:"annonces_ebay",t:"Annonces eBay"},{k:"prix",t:"Prix Amazon",h:x=>`<a href="${e(amz("FR",x.asin))}" target="_blank">${eur(x.prix)}</a>`},{k:"prix_neuf_france",t:"Neuf le moins cher FR",h:x=>x.idealo?`<a href="${e(x.idealo.lien)}" target="_blank">${eur(x.prix_neuf_france)}</a>`:"—"},{k:"origine",t:"Origine",h:x=>`${e(x.origine)}${x.ou_acheter?`<br><b>→ ${e(x.ou_acheter)}</b>`:""}`},{k:"score",t:"Score"}]}):"")+(D.vagues.length?`<h3>Vagues à venir en France</h3><ul>${D.vagues.map(v=>`<li><b>${e(v.mot_cle)}</b> — monte dans ${e((v.monte_dans||[]).join(", "))}</li>`).join("")}</ul>`:"");}
 else if(actif==="demande"){html=`<div class="vide">Recherches en forte hausse sur idealo en France, Allemagne, Espagne et Italie (Amigo, mise à jour ${e(D.demande_maj)}). Pour les 10 premières de chaque pays : le moins cher, le plus cher et le prix par pays de la meilleure vente sur Amazon${D.prix_recherches_maj?` (Keepa, ${e(D.prix_recherches_maj)})`:""}. La colonne Pays indique où c'est le plus recherché.</div>`+cadre("demande",{lignes:D.demande,tri:"popularite",tris:[["Popularité","popularite",-1],["Hausse","hausse",-1],["Moins cher","prix_min",1],["Plus cher","prix_max",-1],["Ventes Amazon","ventes",-1],["Promos vues","nb_vues",-1]],filtres:[["Pays","pays_top"]],puces:[["Top 10 de chaque pays",x=>x.top10],["Avec prix",x=>x.prix_min!=null],["Nouveau",x=>x.nouveau]],
  cols:[{k:"recherche",t:"Recherche",h:x=>`${x.top10?'<span class="badge orange">TOP 10</span>':""}${x.nouveau?'<span class="badge vert">nouveau</span>':""}<b>${e(x.recherche)}</b>`},{k:"popularite",t:"Popularité",h:x=>`<b>${e(x.popularite)}</b>`},{k:"hausse",t:"Hausse",h:x=>x.hausse!=null?`+${e(x.hausse)} %`:"—"},{k:"pays_top",t:"Pays",h:x=>Object.entries(x.pays).sort((a,b)=>(b[1]||0)-(a[1]||0)).map(([p,v])=>`${e(p)} ${e(v)}`).join("<br>")},{k:"prix_min",t:"Moins cher",h:x=>x.moins_cher?`<a href="${e(x.moins_cher.lien)}" target="_blank"><b>${eur(x.moins_cher.prix)}</b></a><br><small>${e((x.moins_cher.titre||"").slice(0,55))}</small>`:"—"},{k:"prix_max",t:"Plus cher",h:x=>x.plus_cher?`<a href="${e(x.plus_cher.lien)}" target="_blank"><b>${eur(x.plus_cher.prix)}</b></a><br><small>${e((x.plus_cher.titre||"").slice(0,55))}</small>`:"—"},{k:"ventes",t:"Meilleure vente",h:x=>x.meilleure_vente?`<a href="${e(x.meilleure_vente.lien)}" target="_blank">${e((x.meilleure_vente.titre||"").slice(0,55))}</a><br><small>${e(x.meilleure_vente.ventes_30j??"?")} ventes/mois · ${e(x.meilleure_vente.vendeurs??"?")} vendeurs</small>`:"—"},{k:"par_pays",t:"Prix par pays",tri:false,h:x=>x.par_pays?Object.entries(x.par_pays).sort((a,b)=>a[1].prix-b[1].prix).map(([p,v])=>`<a href="${e(v.lien)}" target="_blank">${e(p)} ${eur(v.prix)}</a>`).join("<br>"):"—"},{k:"nb_vues",t:"Promos vues",h:x=>x.vues.length?x.vues.map(v=>`<a href="${e(v.lien)}" target="_blank">${eur(v.prix)} — ${e((v.titre||"").slice(0,60))}</a>`).join("<br>"):"—"},{k:"liens",t:"Liens",tri:false,h:x=>liens(x.recherche,null,x.pays_top)}]});}
 else if(actif==="arbitrage"){const A=D.arbitrage||[];const forts=A.filter(x=>x.ecart_pct>=65).sort((a,b)=>b.ecart_pct-a.ecart_pct);html=`<div class="vide">Même produit moins cher sur Amazon Allemagne / Italie / Espagne qu'en France, port compris (Keepa, ${e(D.arbitrage_total)} produits comparés, mise à jour ${e(D.arbitrage_maj||"pas encore")}). « Écart réel » compare au prix le plus bas entre Amazon.fr et sa moyenne 90 jours : c'est lui qui compte. « Marge estimée » = 85 % de ce prix moins le coût rendu. Trouvé par Amigo.</div>`+(forts.length?`<h3>À approfondir : écart de 65 % et plus (${forts.length})</h3>`+forts.map(carteArb).join(""):"")+`<h3>Tous les écarts</h3>`+(A.length?cadre("arbitrage",{lignes:A,tri:"marge_estimee",tris:[["Marge estimée","marge_estimee",-1],["Écart","ecart_pct",-1],["Écart réel","ecart_reel",-1],["Ventes 30 j","ventes_30j_fr",-1],["Moins de vendeurs","vendeurs_fr",1],["Prix d'achat","prix_achat",1]],filtres:[["Pays d'achat","pays_achat"],["Marque","marque"],["Avis","verdict"]],puces:[["Écart ≥ 65 %",x=>x.ecart_pct>=65],["Écart réel ≥ 30 %",x=>x.ecart_reel>=30],["Prix FR fiable",x=>!x.douteux]],
  cols:[{k:"titre",t:"Produit",h:x=>`<a href="${e(x.lien_fr)}" target="_blank">${e((x.titre||"").slice(0,90))}</a>${x.douteux?'<br><span class="badge rouge">prix FR à vérifier</span>':""}${x.verdict?`<br><span class="badge ${x.verdict==="à tester"?"orange":"rouge"}">${e(x.verdict)}</span>`:""}`},{k:"pays_achat",t:"Acheter",h:x=>`<a href="${e(x.lien_achat)}" target="_blank">Amazon ${e(x.pays_achat)}</a>`},{k:"prix_achat",t:"Prix là-bas",h:x=>eur(x.prix_achat)},{k:"cout_rendu",t:"Rendu FR",h:x=>eur(x.cout_rendu)},{k:"prix_fr",t:"Amazon.fr",h:x=>eur(x.prix_fr)},{k:"moyenne_90j_fr",t:"Moyenne 90 j",h:x=>eur(x.moyenne_90j_fr)},{k:"ecart_pct",t:"Écart",h:x=>`<b>-${e(x.ecart_pct)} %</b>`},{k:"ecart_reel",t:"Écart réel",h:x=>x.ecart_reel!=null?`-${e(x.ecart_reel)} %`:"—"},{k:"marge_estimee",t:"Marge estimée",h:x=>mg(x.marge_estimee)},{k:"ventes_30j_fr",t:"Ventes 30 j FR"},{k:"vendeurs_fr",t:"Vendeurs FR"},{k:"liens",t:"Liens",tri:false,h:x=>liens(x.titre,x.ean)}]}):"<p>Première comparaison en cours (toutes les 10 minutes).</p>");}
 else if(actif==="sourceur"){const S=D.sourcing||[];html=`<div class="vide">Le Sourceur étudie chaque bingo : où il est fabriqué, qui le distribue, quel grossiste ou quelle usine, à quel prix, et un message de négociation prêt à envoyer (${e(S.length)} fiches, mise à jour ${e(D.sourcing_maj||"pas encore")}). Rien n'est envoyé automatiquement : c'est toi qui contactes.</div>`+cadre("sourceur",{lignes:S,tri:"recherches_mois",tris:[["Recherches","recherches_mois",-1],["Marge possible","marge_possible_pct",-1],["Prix FR","prix_fr",1],["Prix d'achat cible","prix_achat_cible_eur",1],["Moins de vendeurs","vendeurs",1]],filtres:[["Type","type"]],rendu:carteSource});}
 else if(actif==="chasseur"){const C=D.chasse||[];html=`<div class="vide">Annonces de particuliers (Vinted, Leboncoin) trouvées par le Chasseur sur ton PC : sous-cotées (≤ 65 % du prix d'occasion), invisibles (titre mal écrit, lot) ou vendeur pressé. Mise à jour ${e(D.chasse_maj||"pas encore : attend le collecteur PC")} · ${e((D.chasse_etat||{}).recherches||0)} recherches, ${e((D.chasse_etat||{}).annonces_lues||0)} annonces lues au dernier tour.</div>`+(C.length?cadre("chasseur",{lignes:C,tri:"ecart_pct",tris:[["Écart","ecart_pct",-1],["Prix","prix",1],["Référence","reference",-1],["Plus récent","vu",-1]],filtres:[["Site","site"]],
  cols:[{k:"site",t:"Site"},{k:"titre",t:"Annonce",h:x=>`<a href="${e(x.lien)}" target="_blank">${e(x.titre)}</a>`},{k:"prix",t:"Prix",h:x=>`<b>${eur(x.prix)}</b>`},{k:"reference",t:"Référence occasion",h:x=>eur(x.reference)},{k:"ecart_pct",t:"Écart",h:x=>x.ecart_pct!=null?`-${e(x.ecart_pct)} %`:"—"},{k:"signaux",t:"Signaux",tri:false,h:x=>e((x.signaux||[]).join(", "))},{k:"produit",t:"Produit cherché",h:x=>`${e(x.produit)} <small>(${e(x.origine)})</small>`},{k:"vu",t:"Vu",h:x=>e((x.vu||"").slice(5,16).replace("T"," "))}]}):"");}
 else if(actif==="pays"){const P=D.demande_pays||{};const noms={FR:"🇫🇷 France",DE:"🇩🇪 Allemagne",ES:"🇪🇸 Espagne",IT:"🇮🇹 Italie",US:"🇺🇸 USA",JP:"🇯🇵 Japon"};const L=[];for(const [p,v] of Object.entries(P))(v.top||[]).slice(0,30).forEach(x=>L.push({...x,pays:noms[p]||p}));
   html=`<div class="vide">Volume de recherches Google par pays (Amigo, DataForSEO, hebdomadaire — ${e(D.demande_pays_maj||"pas encore calculé")}) sur les produits de la base, croisé avec leur prix : qui cherche quoi, et dans quelle tranche de prix.</div>`;
   if(L.length)html+=cadre("pays",{lignes:L,tri:"volume",tris:[["Recherches","volume",-1],["Prix","prix",1],["Moins de vendeurs","vendeurs_amazon_fr",1]],filtres:[["Pays","pays"]],cols:[{k:"pays",t:"Pays"},{k:"mot_cle",t:"Produit (mot-clé)",h:x=>`<b>${e(x.mot_cle)}</b><br><small>${e(x.titre)}</small>`},{k:"volume",t:"Recherches / mois",h:x=>`<b>${e(x.volume)}</b>`},{k:"prix",t:"Prix",h:x=>eur(x.prix)},{k:"vendeurs_amazon_fr",t:"Vendeurs Amazon FR"},{k:"liens",t:"Liens",tri:false,h:x=>liens(x.titre||x.mot_cle)}]});
   for(const [p,v] of Object.entries(P)){html+=`<h3>${noms[p]||p} — ${e(v.nb_avec_volume)} produits avec volume</h3><table><tr><th>Tranche de prix</th><th>Produits</th><th>Recherches / mois</th></tr>`+Object.entries(v.tranches||{}).map(([t,x])=>`<tr><td>${e(t)}</td><td>${e(x.produits)}</td><td><b>${e(x.recherches)}</b></td></tr>`).join("")+"</table>";}
   if(!Object.keys(P).length)html+="<p>Première récolte lundi prochain (ou lancement manuel).</p>";}
 else if(actif==="outils"){html=`<table><tr><th>Outil</th><th>Consommé</th><th>Plafond</th><th>Appels</th></tr>`+D.outils.map(o=>`<tr><td>${e(o.outil)}</td><td>${e(o.mois)}</td><td>${e(o.plafond)}</td><td>${e(o.appels)}</td></tr>`).join("")+"</table>";}
 document.getElementById("s_"+actif).innerHTML=html;document.getElementById("compte").textContent=n?`${n} ligne(s)`:"";if(CFG[actif]&&document.getElementById("t_"+actif))majTable(actif);window.scrollTo(0,0);}
function hauteurNav(){document.documentElement.style.setProperty("--nav",document.getElementById("nav").offsetHeight+"px");}addEventListener("resize",hauteurNav);hauteurNav();
rendre();
</script></body></html>"""


if __name__ == "__main__":
    construire()
