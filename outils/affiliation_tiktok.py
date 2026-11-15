"""AFFILIATION TIKTOK SHOP : quels produits promouvoir en vidéo ? (demande de David, 15/11/2026)

Chaîne (4 sources prouvées le 15/11/2026 par de vrais relevés) :
 1. classement des ventes TikTok Shop France sur 7 jours, avec la commission d'affiliation (robot Apify « tiktok_top ») ;
 2. tri : gain par vente (prix moyen × commission), volume, évolution -> quelques finalistes, un par catégorie et par marque ;
 3. pour chaque finaliste : prix réellement vendus sur ebay.fr (robot « ebay_vendus »), pubs Facebook / Instagram / Google
    en cours (robot « pubs » : une pub payée depuis des semaines = un produit qui se vend), prix Amazon.fr (Keepa).
Aucun chiffre inventé : une donnée absente est écrite « non trouvé ». Les montants TikTok sont des ESTIMATIONS du
fournisseur de données, en dollars (à utiliser pour comparer les produits entre eux).

Coût : ≈ 0,40 $ par relevé (plafond du jour « T » dans denicheur/apify.py), Keepa ≈ 10 jetons par finaliste.
Lancement : outil = affiliation_tiktok  ->  data/affiliation_tiktok.html + data/affiliation_tiktok.json + Telegram
Réglages : config/affiliation_tiktok.json"""
import html as H
import json
import os
import re
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from denicheur import apify, keepa, sante, telegram  # noqa: E402

F_CONFIG = os.path.join(RACINE, "config/affiliation_tiktok.json")
F_JSON = os.path.join(RACINE, "data/affiliation_tiktok.json")
F_HTML = os.path.join(RACINE, "data/affiliation_tiktok.html")
MOTS_MARQUE_INUTILES = re.compile(r"\b(officiel(le)?|official|pm|store|shop|france|fr)\b", re.I)


# ---------- calculs purs (testés hors réseau : tests/test_affiliation_tiktok.py) ----------

def nombre(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def marque(titre):
    """Marque probable : le texte entre crochets en tête (« [medicube Officiel] »), sinon le premier mot."""
    titre = (titre or "").strip()
    m = re.match(r"\s*\[([^\]]+)\]", titre)
    if m:
        return re.sub(r"\s+", " ", MOTS_MARQUE_INUTILES.sub(" ", m.group(1))).strip()
    mots = titre.split()
    return mots[0].strip(",;:") if mots else ""


def mot_cle(titre, mots=4):
    """Titre TikTok (très long) -> recherche courte : marque + premiers mots avant le premier séparateur."""
    titre = (titre or "").strip()
    m = marque(titre) if titre.startswith("[") else ""
    corps = re.sub(r"\[[^\]]*\]", " ", titre)
    corps = re.split(r"\s[|–—-]\s|[,(]", corps)[0]
    return " ".join(([m] if m else []) + corps.split()[:mots]).strip()


PAS_UNE_MARQUE = {"LOT", "PACK", "NEW", "PROMO", "KIT", "SET", "XXL", "LED", "USB", "STEM", "PVC", "BLACK", "FRIDAY", "NOEL", "NOËL",
                  "CADEAU", "COFFRET", "OFFRE", "SOLDES", "VARIANTES", "FRANCE", "BIO", "PRO", "MAX", "MINI", "PLUS"}


def marque_fiable(titre):
    """Marque dont on est sûr, sinon "" (relevé du 15/11/2026 : sans marque, eBay, Amazon et les pubs renvoyaient
    d'AUTRES produits — « Coffret de Noël » ramenait un coffret de thés, « Manteau » des annonceurs nommés Manteau).
    Trois cas acceptés : marque entre crochets en tête ; premiers mots tout en majuscules (« LANDOT », « CP PAPILLON ») ;
    un seul mot à majuscule après le dernier « - » (« … - Garnier »)."""
    titre = (titre or "").strip()
    if titre.startswith("["):
        return marque(titre)
    debut = []
    for mot in titre.split():
        m = mot.strip(",;:|")
        if len(m) >= 2 and m.isalpha() and m.isupper() and m not in PAS_UNE_MARQUE:
            debut.append(m)
        else:
            break
    if debut and max(len(m) for m in debut) >= 3:
        return " ".join(debut)
    fin = re.split(r"\s[–—-]\s", titre)
    if len(fin) > 1:
        dernier = fin[-1].strip()
        if re.fullmatch(r"[A-ZÀ-Ý][a-zà-ÿ]{2,}", dernier):
            return dernier
    return ""


def recherche(titre, marque_sure, mots=3):
    """Recherche courte et précise : la marque sûre + les premiers mots du produit."""
    corps = re.sub(r"\[[^\]]*\]", " ", titre or "")
    corps = re.split(r"\s[|–—-]\s|[,(]", corps)[0]
    reste = [m for m in corps.split() if m.strip(",;:").lower() not in {x.lower() for x in marque_sure.split()}]
    return " ".join([marque_sure] + reste[:mots]).strip()


def _sans_accent(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def garder_ventes(lignes, marque_sure):
    """Ne garde que les ventes eBay dont le titre contient la marque (sinon ce n'est pas le même produit)."""
    m = _sans_accent(marque_sure)
    return [l for l in lignes or [] if isinstance(l, dict) and m and m in _sans_accent(l.get("title"))]


def garder_pubs(lignes, marque_sure):
    """Ne garde que les pubs de la marque : annonceur dont le nom COMMENCE par la marque, ou lien qui la contient
    (« Sébastien Roland Jean LANDOT » est une personne, pas la marque LANDOT)."""
    m = _sans_accent(marque_sure).replace(" ", "")
    bons = []
    for l in lignes or []:
        if not isinstance(l, dict) or not m:
            continue
        nom = _sans_accent(l.get("advertiserName") or l.get("resolvedBrand")).replace(" ", "")
        lien = _sans_accent(str(l.get("landingUrl") or "") + " " + str(l.get("destinationDomain") or "")).replace("-", "")
        if nom.startswith(m) or m in lien:
            bons.append(l)
    return bons


def categorie_principale(texte):
    """Le robot renvoie toute la liste des sous-catégories (« Home Supplies | Home Supplies-Home Decor | … ») : on garde la première."""
    return str(texte or "").split(" | ")[0].strip()


def lire_produit(ligne):
    """Une ligne du robot TikTok -> produit normalisé, ou None si ce n'est pas une ligne produit (notice, erreur)."""
    if not isinstance(ligne, dict) or not ligne.get("title"):
        return None
    ventes, prix, com = nombre(ligne.get("unitsSold")), nombre(ligne.get("avgSellingPrice")), nombre(ligne.get("commissionRatePercent"))
    if ventes is None or prix is None or com is None:
        return None
    revenu = nombre(ligne.get("revenue")) or 0.0
    video = nombre(ligne.get("videoRevenue"))
    return {
        "titre": str(ligne["title"]).strip(),
        "marque": marque(ligne["title"]),
        "categorie": categorie_principale(ligne.get("category") or ligne.get("sourceInput")),
        "rang": ligne.get("rank"),
        "ventes_7j": int(ventes),
        "prix_moyen_usd": round(prix, 2),
        "commission_pct": com,
        "gain_par_vente_usd": round(prix * com / 100, 2),
        "revenu_usd": round(revenu),
        "commissions_totales_usd": round(revenu * com / 100),
        "part_video_pct": round(100 * video / revenu) if video is not None and revenu > 0 else None,
        "evolution_pct": nombre(ligne.get("revenueGrowthPercent")),
        "lien": ligne.get("url") or "",
    }


def retenu(p, filtres):
    """Renvoie (True, "") ou (False, raison écrite pour David)."""
    if p["prix_moyen_usd"] < filtres["prix_moyen_min_usd"]:
        return False, "prix moyen trop bas (donnée douteuse ou gain infime)"
    if p["ventes_7j"] < filtres["ventes_min"]:
        return False, "trop peu de ventes"
    if p["evolution_pct"] is not None and p["evolution_pct"] < filtres["evolution_min_pct"]:
        return False, "ventes en recul"
    if p["gain_par_vente_usd"] < filtres["gain_par_vente_min_usd"]:
        return False, "gain par vente trop faible"
    return True, ""


def choisir_finalistes(produits, filtres, n=3):
    """Les n meilleurs par commissions totales estimées, en variant les catégories puis les marques."""
    bons = sorted((p for p in produits if retenu(p, filtres)[0]), key=lambda p: -p["commissions_totales_usd"])
    choisis, marques, categories = [], set(), set()
    for passe in (1, 2):  # passe 1 : une catégorie et une marque différentes ; passe 2 : seulement une marque différente
        for p in bons:
            if len(choisis) >= n:
                return choisis
            m = p["marque"].lower()
            if p in choisis or m in marques or (passe == 1 and p["categorie"] in categories):
                continue
            choisis.append(p)
            marques.add(m)
            categories.add(p["categorie"])
    return choisis


def resume_ebay(lignes):
    prix = [x for x in (nombre(l.get("soldPrice")) for l in lignes or [] if isinstance(l, dict)) if x]
    if not prix:
        return None
    return {"nb": len(prix), "min": min(prix), "mediane": round(statistics.median(prix), 2), "max": max(prix),
            "devise": next((l.get("soldCurrency") for l in lignes if isinstance(l, dict) and l.get("soldCurrency")), "EUR")}


def resume_pubs(lignes):
    pubs = [l for l in lignes or [] if isinstance(l, dict) and l.get("platform")]
    if not pubs:
        return None
    jours = [int(j) for j in (nombre(l.get("daysRunning")) for l in pubs) if j is not None]
    annonceurs = {}
    for l in pubs:
        a = str(l.get("advertiserName") or l.get("resolvedBrand") or "").strip()
        if a:
            annonceurs[a] = annonceurs.get(a, 0) + 1
    vers_amazon = sum(1 for l in pubs if "amazon." in str(l.get("landingUrl") or l.get("destinationDomain") or ""))
    return {"nb": len(pubs), "plus_longue_jours": max(jours) if jours else None,
            "depuis_30j_ou_plus": sum(1 for j in jours if j >= 30),
            "annonceurs": sorted(annonceurs, key=lambda a: -annonceurs[a])[:3], "vers_amazon": vers_amazon}


# ---------- réseau ----------

def taux_usd_eur():
    """Taux du jour de la BCE (gratuit). None si injoignable : on garde alors les dollars seuls."""
    try:
        with urllib.request.urlopen("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=15) as r:
            return float(json.loads(r.read())["rates"]["EUR"])
    except Exception:
        return None


def depense_apify():
    apify._reel.clear()
    return apify.depense_reelle()


def enrichir(p, cfg):
    m = marque_fiable(p["titre"])
    p["marque_sure"] = m
    p.update({"ebay": None, "ebay_lu": False, "pubs": None, "pubs_lu": False, "pubs_terme": m, "amazon": None, "recherche": ""})
    if not m:
        return p  # sans marque sûre, aucun recoupement : mieux vaut « non fait » qu'un autre produit
    q = recherche(p["titre"], m)
    p["recherche"] = q
    ventes = apify.lancer("ebay_vendus", {"keywords": [q], "ebaySite": "ebay.fr", "count": cfg["ebay"]["ventes_par_finaliste"],
                                          "daysToScrape": cfg["ebay"]["jours"]}, maxi=cfg["ebay"]["ventes_par_finaliste"])
    p["ebay"] = resume_ebay(garder_ventes(ventes, m))
    p["ebay_lu"] = ventes is not None
    pubs = apify.lancer("pubs", {"mode": "discovery", "searchQuery": [m], "domains": [], "region": cfg["pubs"]["region"],
                                 "includeMeta": True, "includeTikTok": False, "maxItems": cfg["pubs"]["pubs_par_finaliste"],
                                 "rehostMetaMedia": False, "rehostGoogleVideos": False, "rehostTikTokMedia": False,
                                 "includeAdvertiserInfo": False}, maxi=cfg["pubs"]["pubs_par_finaliste"])
    p["pubs"] = resume_pubs(garder_pubs(pubs, m))
    p["pubs_lu"] = pubs is not None
    if cfg.get("keepa"):
        f = sante.protege("affiliation keepa", keepa.rechercher, q, "FR")
        if (isinstance(f, dict) and not f.get("erreur") and f.get("prix_neuf")
                and _sans_accent(m) in _sans_accent(f.get("titre"))):
            p["amazon"] = {"prix_neuf_eur": f.get("prix_neuf"), "asin": f.get("asin"), "titre": f.get("titre"),
                           "rang_ventes": f.get("rang_ventes")}
    return p


# ---------- rapport ----------

def _usd(v, taux):
    if v is None:
        return "non trouvé"
    s = f"{v:,.2f} $".replace(",", " ").replace(".", ",") if v < 1000 else f"{v:,.0f} $".replace(",", " ")
    return s + (f" (≈ {v * taux:,.2f} €)".replace(",", " ").replace(".", ",") if taux and v < 1000 else "")


def _eur(v):
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _evo(v):
    return "inconnue" if v is None else f"{'+' if v >= 0 else ''}{v:.0f} %"


def carte(p, taux):
    e, pb, am = p.get("ebay"), p.get("pubs"), p.get("amazon")
    non_lu = "non lu (budget du jour atteint ou robot indisponible)"
    if not p.get("marque_sure"):
        ebay = pubs = amazon = "non recoupé : produit sans marque identifiable (risque de confondre avec un autre article)"
    else:
        if e:
            ebay = (f"{e['nb']} vente(s) de la marque sur 30 jours : de {_eur(e['min'])} à {_eur(e['max'])} {e['devise']}"
                    f" (médiane {_eur(e['mediane'])})")
        else:
            ebay = f"aucune vente trouvée sur ebay.fr pour « {H.escape(p.get('recherche', ''))} »" if p.get("ebay_lu") else non_lu
        if pb:
            pubs = (f"{pb['nb']} pub(s) de la marque « {H.escape(p['pubs_terme'])} »"
                    + (f", la plus ancienne tourne depuis {pb['plus_longue_jours']} jours" if pb["plus_longue_jours"] is not None else "")
                    + (f", {pb['depuis_30j_ou_plus']} depuis 30 jours ou plus" if pb["depuis_30j_ou_plus"] else "")
                    + (f", {pb['vers_amazon']} renvoient vers Amazon" if pb["vers_amazon"] else "")
                    + (f" — annonceurs : {H.escape(', '.join(pb['annonceurs']))}" if pb["annonceurs"] else ""))
        else:
            pubs = f"aucune pub de la marque « {H.escape(p.get('pubs_terme', ''))} » trouvée" if p.get("pubs_lu") else non_lu
        amazon = (f"{_eur(am['prix_neuf_eur'])} € neuf sur Amazon.fr" + (f" (ASIN {H.escape(str(am['asin']))})" if am.get("asin") else "")
                  if am else f"non trouvé sur Amazon.fr par Keepa pour « {H.escape(p.get('recherche', ''))} »")
    return f"""<div class="carte"><h3><a href="{H.escape(p['lien'])}" target="_blank" rel="noopener">{H.escape(p['titre'][:110])}</a></h3>
<p class="sig">Trouvé par : robot TikTok Shop (Apify) · catégorie {H.escape(p['categorie'] or 'inconnue')} · rang {H.escape(str(p['rang']))}</p>
<table class="kv">
<tr><th>Gain par vente</th><td><b>{_usd(p['gain_par_vente_usd'], taux)}</b> ({p['commission_pct']:g} % de {_usd(p['prix_moyen_usd'], None)})</td></tr>
<tr><th>Ventes sur 7 jours</th><td>{f"{p['ventes_7j']:,}".replace(",", " ")} (évolution {_evo(p['evolution_pct'])})</td></tr>
<tr><th>Commissions totales estimées</th><td>{_usd(p['commissions_totales_usd'], None)} sur 7 jours, tous créateurs confondus</td></tr>
<tr><th>Part des ventes en vidéo</th><td>{'inconnue' if p['part_video_pct'] is None else str(p['part_video_pct']) + ' %'}</td></tr>
<tr><th>Prix vendus sur eBay.fr</th><td>{ebay}</td></tr>
<tr><th>Publicités en cours</th><td>{pubs}</td></tr>
<tr><th>Prix Amazon.fr</th><td>{amazon}</td></tr>
</table></div>"""


def rapport(tous, finalistes, cfg, taux, cout, quand):
    lignes = []
    for p in tous:
        ok, raison = retenu(p, cfg["filtres"])
        lignes.append({**{k: p[k] for k in ("titre", "marque", "categorie", "ventes_7j", "prix_moyen_usd", "commission_pct",
                                              "gain_par_vente_usd", "commissions_totales_usd", "evolution_pct", "lien")},
                       "etat": "finaliste" if p in finalistes else ("retenu" if ok else raison)})
    cout_txt = "non mesuré" if cout is None else f"{cout:.3f} $".replace(".", ",")
    page = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Affiliation TikTok Shop</title>
<style>
body{{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1c1f24}}
header{{padding:16px 20px;background:#111;color:#fff}} header p{{margin:4px 0 0;color:#cfd3da;font-size:14px}}
nav{{display:flex;gap:6px;padding:10px 20px;background:#fff;border-bottom:1px solid #dde1e7;position:sticky;top:0}}
nav button{{padding:8px 14px;border:1px solid #c9ced6;background:#fff;border-radius:6px;cursor:pointer;font-size:14px}}
nav button.on{{background:#111;color:#fff;border-color:#111}}
main{{padding:16px 20px;max-width:1200px;margin:auto}} section{{display:none}} section.on{{display:block}}
.carte{{background:#fff;border:1px solid #dde1e7;border-radius:8px;padding:14px 16px;margin:0 0 14px}}
.carte h3{{margin:0 0 4px;font-size:17px}} .sig{{margin:0 0 10px;color:#5b6370;font-size:13px}}
.kv th{{text-align:left;font-weight:500;color:#5b6370;padding:3px 14px 3px 0;vertical-align:top;white-space:nowrap}} .kv td{{padding:3px 0}}
table.liste{{border-collapse:collapse;width:100%;background:#fff;font-size:14px}}
table.liste th,table.liste td{{border-bottom:1px solid #e3e6eb;padding:7px 9px;text-align:left}}
table.liste th{{cursor:pointer;background:#eef0f3;user-select:none;white-space:nowrap}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.filtres{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 12px}} .filtres input,.filtres select{{padding:7px 9px;border:1px solid #c9ced6;border-radius:6px;font-size:14px}}
.note{{color:#5b6370;font-size:13px}} a{{color:#0b57d0}} .f{{font-weight:600;color:#0a7a3d}}
</style>
<header><h1 style="margin:0;font-size:21px">Affiliation TikTok Shop France</h1>
<p>Relevé du {quand} · {len(tous)} produits lus · {len(finalistes)} finaliste(s) · coût Apify mesuré : {cout_txt}</p></header>
<nav><button class="on" data-t="fin">Finalistes</button><button data-t="tous">Tous les produits</button><button data-t="lire">Comment lire</button></nav>
<main>
<section id="fin" class="on">{''.join(carte(p, taux) for p in finalistes)}</section>
<section id="tous"><div class="filtres"><input id="q" placeholder="Chercher un produit ou une marque" size="32">
<select id="cat"><option value="">Toutes les catégories</option></select>
<select id="etat"><option value="">Tous</option><option value="ok">Retenus et finalistes</option><option value="non">Écartés</option></select></div>
<table class="liste"><thead><tr><th data-k="titre">Produit</th><th data-k="categorie">Catégorie</th><th data-k="ventes_7j">Ventes 7 j</th>
<th data-k="prix_moyen_usd">Prix moyen ($)</th><th data-k="commission_pct">Commission</th><th data-k="gain_par_vente_usd">Gain par vente ($)</th>
<th data-k="commissions_totales_usd">Commissions totales ($)</th><th data-k="evolution_pct">Évolution</th><th data-k="etat">Verdict</th></tr></thead><tbody id="tb"></tbody></table></section>
<section id="lire"><div class="carte"><h3>Comment lire ce rapport</h3>
<p><b>Gain par vente</b> : prix moyen × commission. C'est ce que touche le créateur pour une vente, avant annulation en cas de retour.</p>
<p><b>Commissions totales estimées</b> : revenu estimé × commission, tous créateurs confondus. Cela mesure où se trouve l'argent, pas ce que tu toucheras.</p>
<p><b>Finalistes</b> : les {cfg['finalistes']} produits au plus fort total de commissions, une catégorie et une marque différentes à chaque fois, après avoir écarté
les prix moyens sous {cfg['filtres']['prix_moyen_min_usd']} $, les produits à moins de {cfg['filtres']['ventes_min']} ventes, les ventes en recul de plus de {abs(cfg['filtres']['evolution_min_pct'])} % et les gains par vente sous {cfg['filtres']['gain_par_vente_min_usd']} $.</p>
<p class="note">Les ventes et revenus TikTok sont des estimations du fournisseur de données, en dollars : ils servent à comparer les produits entre eux.
Le taux de commission est celui annoncé par le robot ; vérifie-le dans ton catalogue créateur avant de tourner la vidéo.
{'Conversion en euros au taux BCE du jour : 1 $ = ' + format(taux, '.4f').replace('.', ',') + ' €.' if taux else 'Conversion en euros indisponible aujourd’hui : montants en dollars seuls.'}</p></div></section>
</main>
<script>
const D={json.dumps(lignes, ensure_ascii=False).replace("</", "<\\/")};
let tri="commissions_totales_usd",sens=-1;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));
const fr=(v,d)=>v==null?"inconnue":Number(v).toLocaleString("fr-FR",{{minimumFractionDigits:d,maximumFractionDigits:d}});
const cats=[...new Set(D.map(x=>x.categorie).filter(Boolean))].sort();
document.getElementById("cat").innerHTML+=cats.map(c=>`<option>${{esc(c)}}</option>`).join("");
function dessiner(){{
  const q=document.getElementById("q").value.toLowerCase(),c=document.getElementById("cat").value,e=document.getElementById("etat").value;
  const ok=x=>x.etat==="finaliste"||x.etat==="retenu";
  const L=D.filter(x=>(!q||(x.titre+" "+x.marque).toLowerCase().includes(q))&&(!c||x.categorie===c)&&(!e||(e==="ok")===ok(x)));
  L.sort((a,b)=>{{const x=a[tri],y=b[tri];if(x==null)return 1;if(y==null)return -1;return (typeof x==="number"?x-y:String(x).localeCompare(String(y),"fr"))*sens}});
  document.getElementById("tb").innerHTML=L.map(x=>`<tr><td><a href="${{esc(x.lien)}}" target="_blank" rel="noopener">${{esc(x.titre.slice(0,80))}}</a></td><td>${{esc(x.categorie)}}</td>
<td class="n">${{fr(x.ventes_7j,0)}}</td><td class="n">${{fr(x.prix_moyen_usd,2)}}</td><td class="n">${{fr(x.commission_pct,0)}} %</td><td class="n">${{fr(x.gain_par_vente_usd,2)}}</td>
<td class="n">${{fr(x.commissions_totales_usd,0)}}</td><td class="n">${{x.evolution_pct==null?"inconnue":(x.evolution_pct>=0?"+":"")+fr(x.evolution_pct,0)+" %"}}</td>
<td class="${{ok(x)?"f":""}}">${{esc(x.etat)}}</td></tr>`).join("");
}}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{{document.querySelectorAll("nav button,section").forEach(x=>x.classList.remove("on"));b.classList.add("on");document.getElementById(b.dataset.t).classList.add("on")}});
document.querySelectorAll("th[data-k]").forEach(t=>t.onclick=()=>{{sens=tri===t.dataset.k?-sens:-1;tri=t.dataset.k;dessiner()}});
["q","cat","etat"].forEach(i=>document.getElementById(i).oninput=dessiner);
dessiner();
</script></html>"""
    with open(F_HTML, "w", encoding="utf-8") as f:
        f.write(page)


def message_telegram(finalistes, taux, n_lus):
    blocs = [f"<b>Affiliation TikTok Shop</b> — {n_lus} produits lus, {len(finalistes)} à tester en vidéo :"]
    for i, p in enumerate(finalistes, 1):
        e, pb = p.get("ebay"), p.get("pubs")
        blocs.append(f"\n{i}. <a href=\"{H.escape(p['lien'])}\">{H.escape(p['titre'][:70])}</a>\n"
                     f"Gain par vente : {_usd(p['gain_par_vente_usd'], taux)} ({p['commission_pct']:g} %) · {p['ventes_7j']} ventes sur 7 j ({_evo(p['evolution_pct'])})\n"
                     + ("" if p.get("marque_sure") else "Recoupement eBay, Amazon et pubs non fait : pas de marque identifiable\n")
                     + (f"eBay.fr : {e['nb']} vente(s), médiane {_eur(e['mediane'])} {e['devise']}\n" if e else "")
                     + (f"Pubs de la marque : {pb['nb']}" + (f", la plus ancienne depuis {pb['plus_longue_jours']} j" if pb['plus_longue_jours'] is not None else "") + "\n" if pb else ""))
    return "".join(blocs)


def main():
    cfg = json.load(open(F_CONFIG, encoding="utf-8"))
    apify.CONTEXTE["denicheur"] = "T"
    avant = depense_apify()
    n = len(cfg["categories"]) * cfg["produits_par_categorie"]
    jour = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y")
    deja = None
    if cfg.get("reutiliser_classement_du_jour", True):
        try:
            ancien = json.load(open(F_JSON, encoding="utf-8"))
            if str(ancien.get("quand", "")).startswith(jour) and ancien.get("tous"):
                deja = ancien["tous"]  # le classement TikTok ne se paie qu'une fois par jour
        except (OSError, json.JSONDecodeError):
            pass
    brut = [] if deja else apify.lancer("tiktok_top", {"country": cfg["pays"], "period": cfg["periode"], "sortBy": cfg["tri"],
                                       "categories": cfg["categories"], "maxResultsPerSource": cfg["produits_par_categorie"],
                                       "addAnalytics": False}, maxi=n + len(cfg["categories"]))
    if brut is None:
        sante.noter("erreur", "affiliation tiktok", "classement TikTok non lu (budget du jour ou du mois atteint, jeton absent, ou robot en erreur)")
        print("Classement TikTok non lu : aucun rapport écrit.")
        return 1
    vus, tous = set(), []
    cles = ("titre", "marque", "categorie", "rang", "ventes_7j", "prix_moyen_usd", "commission_pct", "gain_par_vente_usd",
            "revenu_usd", "commissions_totales_usd", "part_video_pct", "evolution_pct", "lien")
    for p in deja or []:
        p = {k: p.get(k) for k in cles}
        p["categorie"] = categorie_principale(p["categorie"])
        vus.add(p["lien"])
        tous.append(p)
    for ligne in brut:
        p = lire_produit(ligne)
        if p and p["lien"] not in vus:
            vus.add(p["lien"])
            tous.append(p)
    if not tous:
        sante.noter("erreur", "affiliation tiktok", f"{len(brut)} ligne(s) reçue(s) mais aucun produit lisible")
        print("Aucun produit lisible : aucun rapport écrit.")
        return 1
    finalistes = choisir_finalistes(tous, cfg["filtres"], cfg["finalistes"])
    for p in finalistes:
        sante.protege("affiliation enrichir", enrichir, p, cfg)
    apres = depense_apify()
    cout = round(apres - avant, 4) if avant is not None and apres is not None else None
    taux = taux_usd_eur()
    quand = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y à %H h %M")
    par_cat = {}
    for p in tous:
        par_cat[p["categorie"]] = par_cat.get(p["categorie"], 0) + 1
    json.dump({"quand": quand, "classement_reutilise": bool(deja), "taux_usd_eur": taux, "cout_apify_mesure_usd": cout, "produits_par_categorie": par_cat,
               "finalistes": finalistes, "tous": tous}, open(F_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(tous)} produits {'repris du relevé du jour' if deja else 'lus'} {par_cat} ; {len(finalistes)} finaliste(s) ; coût Apify mesuré : {cout}")
    for p in finalistes:
        print(" -", p["titre"][:70], "| marque sûre", repr(p.get("marque_sure")), "| recherche", repr(p.get("recherche")), "| gain/vente", p["gain_par_vente_usd"], "$ | ventes", p["ventes_7j"],
              "| eBay", p.get("ebay"), "| pubs", p.get("pubs"), "| Amazon", p.get("amazon"))
    if not finalistes:
        sante.noter("erreur", "affiliation tiktok", f"{len(tous)} produits lus mais aucun ne passe les filtres")
        print("Aucun finaliste : données enregistrées, aucun rapport envoyé.")
        return 1
    rapport(tous, finalistes, cfg, taux, cout, quand)
    telegram.envoyer(message_telegram(finalistes, taux, len(tous)))
    telegram.envoyer_fichier(F_HTML, "Affiliation TikTok Shop : rapport complet (onglets, tri, filtres)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
