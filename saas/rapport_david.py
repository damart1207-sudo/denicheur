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
            "volume_google": (c.get("demande_google") or {}).get("volume_mensuel"), "bingo": bool(c.get("bingo")),
            "date": p.get("horodatage", "").replace("_", " ")[:16], "motif": v.get("commentaire") or (c.get("verification") or {}).get("remarque") or "",
        })

    # --- 2. alertes Idéfix des 24 dernières heures
    alertes = []
    for a in lire("data/alertes.json", []):
        if (a.get("trouve_le") or "") < il_y_a_24h:
            continue
        v = a.get("verdict") or {}
        st = a.get("statut")
        feu = {"valide": "vert", "bon_plan": "orange", "a_verifier": "gris"}.get(st, "rouge")
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
    demande = []
    for x in [x for x in dem.get("liste", []) if x.get("pays") == "FR"][:40]:
        q = mots(x.get("recherche"))
        vues = [r for r in recents if q and q <= mots(r.get("titre"))]
        demande.append({"recherche": x.get("recherche"), "popularite": x.get("popularite"), "hausse": x.get("hausse_pct"),
                        "vues": [{"prix": r.get("prix"), "titre": r.get("titre"), "lien": r.get("lien")} for r in vues[:3]]})

    # --- 7. outils (consommation)
    apify, dfs, keepa, moisson = lire("data/etat/apify_budget.json", {}), lire("data/etat/dataforseo_budget.json", {}), lire("data/etat/keepa_budget.json", {}), lire("data/etat/moisson.json", {})
    outils = [
        {"outil": "Apify (idealo, Leboncoin, Vinted)", "mois": f"{apify.get('depense_reelle_usd', 0):.2f} $ réels / {apify.get('depense_estimee_usd', 0):.2f} $ estimés", "plafond": "35 $/mois", "appels": apify.get("appels")},
        {"outil": "DataForSEO (volumes Google, Trends)", "mois": f"{dfs.get('depense_mois_usd', 0):.2f} $ (aujourd'hui {dfs.get('depense_usd', 0):.2f} $)", "plafond": "0,70 $/jour · dépôt 50 $", "appels": dfs.get("appels")},
        {"outil": "Keepa (fiches + moissonneur)", "mois": f"{moisson.get('jetons_jour', 0)} jetons aujourd'hui, {moisson.get('tours', 0)} récoltes, base {len(lire('data/base/keepa_index.json', {}))} fiches", "plafond": "28 800 jetons/jour (abonnement)", "appels": keepa.get("appels")},
        {"outil": "Gemini (vérification Google)", "mois": f"{(p.get('verification') or {}).get('faits', 0)} vérifications au dernier passage", "plafond": "20 €/mois", "appels": None},
        {"outil": "Tribunal (IA gratuites)", "mois": ", ".join(f"{k} {v['reussites']}/{v['appels'] if v['appels'] < 10**6 else 'coupé'}" for k, v in (p.get("agents") or {}).items()), "plafond": "quotas gratuits", "appels": None},
    ]

    donnees = {"genere": datetime.now(PARIS).strftime("%d/%m/%Y %H:%M"), "passage": p.get("date_affichee"), "resume_audit": audit.get("resume"),
               "affaires": affaires, "alertes": alertes, "radar": radar.get("affaires", [])[:300], "radar_maj": iso_paris(radar.get("maj")),
               "hype": hype.get("produits", []), "hype_maj": iso_paris(hype.get("maj")), "bingo": bingo.get("bingos", []), "bingo_maj": iso_paris(bingo.get("maj")),
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
</style></head><body>
<header><h1>Le Dénicheur — rapport</h1><div class="note" id="entete"></div></header>
<nav id="nav"></nav>
<div class="barre" id="barre">
  <label>Trier <select id="tri"><option value="pertinence">pertinence</option><option value="prix_asc">prix croissant</option><option value="prix_desc">prix décroissant</option><option value="marge">marge</option><option value="economie">% d'économie</option><option value="date">plus récent</option></select></label>
  <label>Feu <select id="feu"><option value="">tous</option><option value="vert">vert</option><option value="orange">orange</option><option value="rouge">rouge</option><option value="gris">à vérifier</option></select></label>
  <label>Dénicheur <select id="den"><option value="">tous</option><option>Idéfix</option><option>Amigo</option><option>Chasseur</option><option>Radar Keepa</option></select></label>
  <label>Pays <select id="pays"><option value="">tous</option></select></label>
  <label>Prix max <input id="pmax" type="number" style="width:80px" placeholder="€"></label>
  <input id="q" type="search" placeholder="rechercher…" style="flex:1;min-width:140px">
</div>
<div class="compte" id="compte"></div>
<section id="s_affaires"></section><section id="s_alertes"></section><section id="s_radar"></section><section id="s_hype"></section>
<section id="s_bingo"></section><section id="s_demande"></section><section id="s_outils"></section>
<script>
const D = __DONNEES__;
const ONGLETS=[["affaires","Affaires du passage"],["alertes","Alertes Idéfix 24 h"],["radar","Radar Keepa"],["hype","Hype étrangère"],["bingo","Bingo"],["demande","Les plus recherchés"],["outils","Outils"]];
const e=t=>String(t??"—").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const eur=v=>typeof v==="number"?v.toFixed(2).replace(".",",")+" €":"—";
let actif="affaires";
document.getElementById("entete").textContent=`Généré le ${D.genere} · dernier passage : ${D.passage||"—"}`+(D.resume_audit?` · Audit : ${D.resume_audit}`:"");
const nav=document.getElementById("nav");
ONGLETS.forEach(([k,n])=>{const b=document.createElement("button");const nb=k==="affaires"?D.affaires.length:k==="alertes"?D.alertes.length:k==="radar"?D.radar.length:k==="hype"?D.hype.length:k==="bingo"?D.bingo.length:k==="demande"?D.demande.length:"";b.textContent=n+(nb!==""?` (${nb})`:"");b.onclick=()=>{actif=k;rendre()};b.dataset.k=k;nav.appendChild(b)});
const paysSel=document.getElementById("pays");[...new Set([...D.affaires,...D.alertes].map(x=>x.pays).filter(Boolean))].sort().forEach(p=>{const o=document.createElement("option");o.textContent=p;paysSel.appendChild(o)});
["tri","feu","den","pays","pmax","q"].forEach(id=>document.getElementById(id).addEventListener("input",rendre));
function filtre(liste){const f=document.getElementById("feu").value,d=document.getElementById("den").value,p=document.getElementById("pays").value,pm=parseFloat(document.getElementById("pmax").value),q=document.getElementById("q").value.toLowerCase();
 return liste.filter(x=>(!f||x.feu===f)&&(!d||x.denicheur===d)&&(!p||x.pays===p)&&(isNaN(pm)||(x.prix??0)<=pm)&&(!q||JSON.stringify(x).toLowerCase().includes(q)));}
function trier(liste){const t=document.getElementById("tri").value;const c=[...liste];
 if(t==="prix_asc")c.sort((a,b)=>(a.prix??1e9)-(b.prix??1e9));else if(t==="prix_desc")c.sort((a,b)=>(b.prix??-1)-(a.prix??-1));
 else if(t==="marge")c.sort((a,b)=>(b.marge??-1e9)-(a.marge??-1e9));else if(t==="economie")c.sort((a,b)=>(b.economie??b.baisse_pct??-1)-(a.economie??a.baisse_pct??-1));
 else if(t==="date")c.sort((a,b)=>String(b.date_iso||b.vu||b.date||"").localeCompare(String(a.date_iso||a.vu||a.date||"")));
 else c.sort((a,b)=>({vert:0,orange:1,gris:2,rouge:3}[a.feu]??2)-({vert:0,orange:1,gris:2,rouge:3}[b.feu]??2)||(b.marge??-1e9)-(a.marge??-1e9));return c;}
function carte(x){const m=x.marge;const cm=typeof m==="number"?`<span class="marge ${m>=8?"pos":m<0?"neg":""}">${m>=0?"+":""}${m.toFixed(2).replace(".",",")} €</span>`:"—";
 return `<div class="carte ${x.feu}"><h3><span class="badge ${x.feu}">${e(x.verdict)}</span><span class="badge den">${e(x.denicheur)}</span>${x.bingo?'<span class="badge orange">BINGO</span>':""}<a href="${e(x.lien)}" target="_blank">${e(x.titre)}</a></h3>
 <div class="ligne"><b>${eur(x.prix)}</b> chez ${e(x.marchand)} (${e(x.pays)})${x.cout?` · coût rendu ${eur(x.cout)}`:""}${x.economie?` · <b>-${x.economie} %</b> vs neuf`:""}</div>
 <div class="ligne">Neuf le moins cher : ${eur(x.neuf_min)}${x.neuf_ou?` (${e(x.neuf_ou)})`:""} · Occasion : ${x.occ_bas||x.occ_haut?`${eur(x.occ_bas)} → ${eur(x.occ_haut)}`:"—"} · Revente retenue : ${eur(x.revente)} sur ${e(x.canal)} · Marge : ${cm}</div>
 <div class="ligne">${x.vendeurs!=null?`vendeurs Amazon : ${x.vendeurs} (concurrence ${e(x.concurrence)}) · `:""}${x.ean?`EAN ${e(x.ean)} · `:""}${x.ventes30!=null?`ventes Amazon 30 j : ${x.ventes30} · `:""}${x.volume_google?`recherches Google : ${x.volume_google}/mois · `:""}${x.duree?`durée : ${e(x.duree)} · `:""}${e(x.date)} · source ${e(x.source)}</div>
 ${x.motif?`<div class="motif">${e(x.motif)}</div>`:""}</div>`;}
function rendre(){document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("actif",b.dataset.k===actif));document.querySelectorAll("section").forEach(s=>s.classList.toggle("actif",s.id==="s_"+actif));
 document.getElementById("barre").style.display=["affaires","alertes","radar"].includes(actif)?"flex":"none";let html="",n=0;
 if(actif==="affaires"){const l=trier(filtre(D.affaires));n=l.length;html=l.length?l.map(carte).join(""):`<div class="vide">Aucune affaire du passage ne correspond aux filtres.</div>`;if(!D.affaires.some(x=>x.feu==="vert"))html=`<div class="vide">Aucune carte verte à ce passage : voici toutes les affaires examinées avec le motif de l'audit. Les alertes Idéfix des 24 h sont dans l'onglet suivant.</div>`+html;}
 else if(actif==="alertes"){const l=trier(filtre(D.alertes));n=l.length;html=l.length?l.map(carte).join(""):`<div class="vide">Aucune alerte sur 24 h avec ces filtres.</div>`;}
 else if(actif==="radar"){const l=trier(filtre(D.radar.map(a=>({...a,feu:"gris",verdict:a.type,denicheur:"Radar Keepa",pays:"FR",marchand:"Amazon.fr",economie:a.baisse_pct,neuf_min:a.moyenne_90j,neuf_ou:"moyenne 90 j Amazon",date:a.vu,date_iso:a.vu,source:"keepa-radar"}))));n=l.length;html=`<div class="vide">Baisses de prix Amazon.fr (mise à jour ${e(D.radar_maj)}) : ce sont des pistes, pas des affaires vérifiées. Chaque baisse entre dans le passage suivant.</div>`+l.map(carte).join("");}
 else if(actif==="hype"){html=`<div class="vide">Meilleures ventes Amazon USA / Japon absentes ou mal vendues en France (mise à jour ${e(D.hype_maj)}). Trouvé par Amigo via Keepa.</div><table><tr><th>Pays</th><th>Produit</th><th>Catégorie</th><th>Ventes 30 j là-bas</th><th>Prix là-bas</th><th>En France</th><th>Prix FR</th></tr>`+D.hype.slice().sort((a,b)=>(b.ventes_30j_labas||0)-(a.ventes_30j_labas||0)).map(x=>`<tr><td>${e(x.pays)}</td><td><a href="${e(x.lien_fr)}" target="_blank">${e((x.titre||"").slice(0,100))}</a></td><td>${e(x.categorie)}</td><td><b>${e(x.ventes_30j_labas)}</b></td><td>${eur(x.prix_labas)}</td><td>${e(x.en_france)}</td><td>${eur(x.prix_fr)}</td></tr>`).join("")+"</table>";}
 else if(actif==="bingo"){html=`<div class="vide">Bingo = très recherché sur Google France (≥ 1 000/mois) ET peu de vendeurs (≤ 5 sur Amazon, ≤ 15 annonces eBay). ${e(D.bingo_info)} (mise à jour ${e(D.bingo_maj)}). Trouvé par Amigo.</div>`+(D.bingo.length?`<table><tr><th>Mot-clé</th><th>Recherches/mois</th><th>Vendeurs Amazon</th><th>Annonces eBay</th><th>Prix</th><th>Origine</th></tr>`+D.bingo.map(x=>`<tr><td><b>${e(x.mot_cle)}</b><br><small>${e((x.titre||"").slice(0,80))}</small></td><td><b>${e(x.recherches_mois)}</b></td><td>${e(x.vendeurs)}</td><td>${e(x.annonces_ebay)}</td><td>${eur(x.prix)}</td><td>${e(x.origine)}</td></tr>`).join("")+"</table>":"")+(D.vagues.length?`<h3>Vagues à venir en France</h3><ul>${D.vagues.map(v=>`<li><b>${e(v.mot_cle)}</b> — monte dans ${e((v.monte_dans||[]).join(", "))}</li>`).join("")}</ul>`:"");}
 else if(actif==="demande"){html=`<div class="vide">Recherches en forte hausse sur idealo.fr (Amigo, mise à jour ${e(D.demande_maj)}) et, pour chacune, les promos vues par Idéfix dont le titre contient tous les mots.</div><table><tr><th>#</th><th>Recherche</th><th>Popularité</th><th>Hausse</th><th>Promos vues</th></tr>`+D.demande.map((x,i)=>`<tr><td>${i+1}</td><td><b>${e(x.recherche)}</b></td><td>${e(x.popularite)}</td><td>+${e(x.hausse)} %</td><td>${x.vues.length?x.vues.map(v=>`<a href="${e(v.lien)}" target="_blank">${eur(v.prix)} — ${e((v.titre||"").slice(0,60))}</a>`).join("<br>"):"—"}</td></tr>`).join("")+"</table>";}
 else if(actif==="outils"){html=`<table><tr><th>Outil</th><th>Consommé</th><th>Plafond</th><th>Appels</th></tr>`+D.outils.map(o=>`<tr><td>${e(o.outil)}</td><td>${e(o.mois)}</td><td>${e(o.plafond)}</td><td>${e(o.appels)}</td></tr>`).join("")+"</table>";}
 document.getElementById("s_"+actif).innerHTML=html;document.getElementById("compte").textContent=n?`${n} ligne(s)`:"";}
rendre();
</script></body></html>"""


if __name__ == "__main__":
    construire()
