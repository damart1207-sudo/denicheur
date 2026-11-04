"""BINGO : produits TRÈS recherchés par les gens et PEU vendus (peu de concurrence) -> partent très vite.

Une fois par jour (passage de la nuit) :  python -m denicheur.bingo
1. Candidats = produits qui se vendent (base Keepa moissonnée, chutes de classement) + hype étrangère + radar Amazon.
2. Demande = volume de recherche Google France (DataForSEO, 1 appel ≈ 0,09 $ pour 1 000 mots, dans le plafond du jour).
3. Concurrence = nombre d'offres neuves sur Amazon.fr (déjà dans la base, gratuit) + annonces eBay.fr (API gratuite)
   pour les meilleurs.
4. Score bingo = recherches mensuelles / (1 + vendeurs). Carte « bingo » quand ≥ 1 000 recherches/mois et ≤ 5 vendeurs.
5. Hype qui monte à l'étranger : Google Trends USA / Japon / Allemagne (DataForSEO, 0,011 $ par appel) sur les 8
   meilleurs produits de la hype Keepa -> « vague à venir en France » quand ça monte là-bas et pas ici.

-> data/bingo.json (lu par l'audit du matin et par le rapport) + data/base/demande/AAAA-MM-JJ.json
Coût : ≈ 0,20 $ par jour au plus, dans le plafond DataForSEO de 0,70 $/jour. Aucun achat.
"""
import json
import os
import re
from datetime import datetime, timezone

from . import base, dataforseo, sante

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_INDEX = os.path.join(RACINE, "data/base/keepa_index.json")
F_HYPE = os.path.join(RACINE, "data/hype_etranger.json")
F_RADAR = os.path.join(RACINE, "data/radar_amazon.json")
F_BINGO = os.path.join(RACINE, "data/bingo.json")
VOLUME_MIN = 1000      # recherches Google France par mois
VENDEURS_MAX = 5       # offres neuves sur Amazon.fr (au-delà : trop de concurrence)
BRUIT = re.compile(r"\b(pour|avec|sans|de|des|et|le|la|les|un|une|du|en|à|noir|blanc|bleu|rouge|gris|vert|rose|"
                   r"compatible|lot|pack|pcs|pièces|set|kit|cm|mm|go|to|version|édition|nouveau|new|original|"
                   r"for|with|and|the|black|white|inch|pouces|\d+(?:[.,]\d+)?\s?(?:cm|mm|go|to|gb|tb|w|kg|g|ml|l|mah|hz|v))\b", re.I)


def _lire(f, defaut):
    try:
        with open(f, encoding="utf-8") as g:
            return json.load(g)
    except (OSError, json.JSONDecodeError):
        return defaut


def mot_cle(titre, marque=None):
    """Titre Amazon (long) -> mot-clé court tel que les gens le tapent : marque + 2-3 mots du modèle."""
    t = re.split(r"[,(|\[\-–:]", titre or "", maxsplit=1)[0]
    t = BRUIT.sub(" ", t)
    mots = [m for m in re.sub(r"[^\w' ]+", " ", t).split() if len(m) > 1 or m.isdigit()]
    if marque and mots and mots[0].lower() != marque.lower():
        mots = [marque] + [m for m in mots if m.lower() != marque.lower()]
    return " ".join(mots[:4]).strip().lower()


F_MOTS = os.path.join(RACINE, "data/base/mots_cles.json")


def mots_cles_ia(titres, maxi_appels=40):
    """Titres Amazon -> ce que les gens TAPENT sur Google (ex. « Razer BlackShark V2 Pro », pas « casque gaming sans fil »).
    Gemini (payant, quelques centimes) par lots de 60 ; chaque titre n'est converti qu'une fois (cache data/base/mots_cles.json).
    Vérifié le 04/11 : les mots-clés mécaniques tirés des titres n'ont aucun volume Google, les vrais noms de produits si."""
    from .ia import Agent, extraire_json
    cache = _lire(F_MOTS, {})
    a_faire = [t for t in dict.fromkeys(titres) if t and t not in cache]
    if a_faire:
        conf = _lire(os.path.join(RACINE, "config/equipe.json"), {}).get("agents", {}).get("gemini")
        if conf:
            agent = Agent("gemini", {**conf, "max_appels": maxi_appels, "timeout": 120})
            for i in range(0, len(a_faire), 60):
                lot = a_faire[i:i + 60]
                if not agent.disponible():
                    break
                lignes = "\n".join(f"{j} | {t[:120]}" for j, t in enumerate(lot))
                rep = agent.demander(
                    "Tu transformes des titres de fiches Amazon en requêtes Google. Réponds en JSON uniquement.",
                    "Pour chaque ligne « numéro | titre », donne la requête courte qu'un acheteur français taperait sur Google pour "
                    "trouver CE produit précis : marque + modèle (2 à 4 mots, minuscules, sans couleur, taille, quantité ni mots génériques). "
                    "Exemples : « Razer BlackShark V2 Pro casque gaming sans fil noir » -> « razer blackshark v2 pro » ; "
                    "« INIU 100W Chargeur USB C 3 ports » -> « iniu chargeur 100w ». Si le titre n'a pas de marque ni de modèle identifiable "
                    "(produit générique), mets null.\n"
                    'Format : {"requetes": [{"n": 0, "q": "..."}]}\n\n' + lignes)
                d = extraire_json(rep) if rep else None
                for x in (d or {}).get("requetes", []):
                    try:
                        n = int(x.get("n"))
                        q = x.get("q")
                        if 0 <= n < len(lot):
                            cache[lot[n]] = (str(q).strip().lower()[:60] if q else None)
                    except (TypeError, ValueError):
                        continue
            os.makedirs(os.path.dirname(F_MOTS), exist_ok=True)
            json.dump(cache, open(F_MOTS, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return cache


def candidats():
    """Produits qui se vendent, avec leur nombre de vendeurs Amazon.fr. {mot_cle: {...}}"""
    idx = _lire(F_INDEX, {})
    bruts = []
    for k, r in idx.items():
        if not k.endswith(":FR") or not r.get("t") or (r.get("ch30") or 0) < 15:
            continue
        bruts.append((r["t"], {"asin": k.split(":")[0], "titre": r["t"], "ean": r.get("ean"), "prix": r.get("neuf"),
                               "ventes_30j": r.get("ch30"), "vendeurs": r.get("offres"), "origine": "etagere"}))
    bruts.sort(key=lambda x: -(x[1].get("ventes_30j") or 0))
    bruts = bruts[:1500]
    for h in _lire(F_HYPE, {}).get("produits", [])[-300:]:
        bruts.append((h.get("titre"), {"asin": h["asin"], "titre": h.get("titre"), "prix": h.get("prix_fr") or h.get("prix_labas"),
                                       "ventes_30j": h.get("ventes_30j_labas"), "vendeurs": 0 if h.get("en_france") == "absent" else None,
                                       "origine": f"hype {h.get('pays')}", "pays_hype": h.get("pays")}))
    for a in _lire(F_RADAR, {}).get("affaires", [])[:150]:
        bruts.append((a.get("titre"), {"asin": a["asin"], "titre": a.get("titre"), "prix": a.get("prix"), "vendeurs": None, "origine": "radar amazon"}))
    cache = mots_cles_ia([t for t, _ in bruts])
    out = {}
    for t, c in bruts:
        mc = cache.get(t) or None
        if not mc or len(mc) < 5 or mc in out:
            continue
        out[mc] = c
    return out


def _ebay_vendeurs(mots, maxi=30):
    """Nombre d'annonces neuves sur eBay.fr (gratuit) pour les meilleurs candidats. {mot: nb}"""
    from . import ebay
    try:
        tok = ebay.jeton()
    except Exception:
        return {}
    res = {}
    for m in mots[:maxi]:
        try:
            prix, _ = ebay.chercher(tok, m, neuf=True, limite=50)
            res[m] = len(prix)
        except Exception:
            continue
    return res


def jour():
    cands = candidats()
    if not cands:
        print("bingo : aucun candidat (la base Keepa est vide pour l'instant)")
        return
    mots = list(cands)[:1000]
    vols = sante.protege("bingo volumes", dataforseo.volumes, mots, "FR", defaut={})
    lignes = []
    for m, c in cands.items():
        v = vols.get(m) or vols.get(m.lower()) or {}
        vol = v.get("volume_mensuel") or 0
        if not vol:
            continue
        vend = c.get("vendeurs")
        score = round(vol / (1 + (vend if isinstance(vend, int) else 10)), 1)
        lignes.append({**c, "mot_cle": m, "recherches_mois": vol, "concurrence_google": v.get("concurrence"),
                       "trois_derniers_mois": v.get("trois_derniers_mois"), "score": score})
    lignes.sort(key=lambda x: -x["score"])
    # concurrence eBay (gratuit) sur les 30 meilleurs
    eb = _ebay_vendeurs([x["mot_cle"] for x in lignes[:30]])
    for x in lignes:
        if x["mot_cle"] in eb:
            x["annonces_ebay"] = eb[x["mot_cle"]]
            x["score"] = round(x["recherches_mois"] / (1 + (x.get("vendeurs") or 0) + eb[x["mot_cle"]] / 5), 1)
        x["bingo"] = (x["recherches_mois"] >= VOLUME_MIN and (x.get("vendeurs") or 0) <= VENDEURS_MAX
                      and x.get("annonces_ebay", 0) <= 15)
    lignes.sort(key=lambda x: (x["bingo"], x["score"]), reverse=True)
    # concurrence réelle en France (idealo via Apify, ≈ 0,01 $ chacun, budget du dénicheur B) sur les 20 meilleurs bingos :
    # nombre de marchands qui vendent le produit + prix neuf le plus bas en France = la cible à battre pour Idéfix/Chasseur.
    from . import apify
    apify.CONTEXTE["denicheur"] = "B"
    for x in [l for l in lignes if l["bingo"]][:10]:
        pi = sante.protege("bingo idealo", apify.prix_idealo, x["mot_cle"], defaut=None)
        if not pi:
            continue
        x["idealo"] = pi
        x["marchands_france"] = pi.get("nb_offres")
        x["prix_neuf_france"] = pi.get("prix_min")
        if isinstance(pi.get("nb_offres"), int) and pi["nb_offres"] >= 10:
            x["bingo"], x["motif"] = False, f"{pi['nb_offres']} marchands en France sur idealo : trop de concurrence"
    apify.CONTEXTE["denicheur"] = "A"
    # où l'acheter moins cher ? prix Amazon par pays (Keepa, 4 jetons par produit) sur les 12 meilleurs bingos avec EAN
    from . import keepa
    for x in [l for l in lignes if l["bingo"] and l.get("ean")][:12]:
        pp = sante.protege("bingo pays", keepa.comparer_pays, x["ean"], ("FR", "DE", "IT", "ES"), defaut={})
        if pp:
            x["prix_par_pays"] = pp
            ref = x.get("prix_neuf_france") or pp.get("FR")
            moins_cher = {p: v for p, v in pp.items() if p != "FR" and ref and v <= ref * 0.85}
            if moins_cher:
                p_min = min(moins_cher, key=moins_cher.get)
                x["ou_acheter"] = f"Amazon {p_min} à {moins_cher[p_min]} € (France {ref} €)"
    lignes.sort(key=lambda x: (x["bingo"], x["score"]), reverse=True)
    # hype qui monte à l'étranger (Google Trends) sur les 8 premiers produits venus de la hype Keepa
    vagues = []
    for x in [l for l in lignes if l.get("pays_hype")][:8]:
        d = sante.protege("bingo tendances", dataforseo.decalage_hype, x["mot_cle"], ("US", "JP", "DE"), "FR", defaut=None)
        if d:
            x["hype"] = d
            if d.get("verdict") == "vague à venir en France":
                vagues.append({"mot_cle": x["mot_cle"], "titre": x["titre"], "monte_dans": d.get("monte_dans"), "asin": x["asin"]})
    bingos = [x for x in lignes if x["bingo"]]
    res = {"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "nb_candidats": len(cands), "nb_avec_volume": len(lignes),
           "bingos": bingos[:60], "vagues": vagues, "meilleurs": lignes[:150]}
    os.makedirs(os.path.dirname(F_BINGO), exist_ok=True)
    json.dump(res, open(F_BINGO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    base.noter_demande([{"pays": "FR", "rang": i + 1, "produit": x["mot_cle"], "source": "google-ads",
                         "volume": x["recherches_mois"], "vendeurs": x.get("vendeurs")} for i, x in enumerate(bingos[:40])], origine="bingo")
    print(f"bingo : {len(cands)} candidats, {len(lignes)} avec volume Google, {len(bingos)} BINGO, {len(vagues)} vague(s) à venir")
    for x in bingos[:5]:
        print(f"  {x['mot_cle']} : {x['recherches_mois']} recherches/mois, {x.get('vendeurs')} vendeurs Amazon, {x.get('annonces_ebay', '?')} annonces eBay")


if __name__ == "__main__":
    jour()


def est_bingo(nom):
    """Pour le passage : ce produit est-il dans les bingos du jour ? Renvoie la ligne bingo ou None."""
    k = base.cle(nom)
    if not k:
        return None
    for x in _lire(F_BINGO, {}).get("bingos", []):
        kb = base.cle(x.get("mot_cle"))
        if kb and (kb in k or k in kb):
            return {"mot_cle": x["mot_cle"], "recherches_mois": x["recherches_mois"], "vendeurs": x.get("vendeurs"), "annonces_ebay": x.get("annonces_ebay")}
    return None
