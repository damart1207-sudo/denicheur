"""FICHE DE DÉCISION d'une annonce (règle de David, 04/11) : tout doit se croiser pour qu'une annonce soit VERTE.
 1. prix le plus bas trouvé (notre achat) face au neuf le moins cher ailleurs ;
 2. concurrence (≥ 10 vendeurs = on passe ; 5-9 seulement si ≥ 15 % moins cher ; ≤ 4 = ok) ;
 3. volume de recherche Google (≥ 1 000 / mois) ;
 4. occasion : prix le plus bas et le plus haut réellement vus (Vinted, Leboncoin, Amazon occasion) ;
 5. prix d'achat maximum pour garder 20 € de bénéfice, et où le revendre ;
 6. bénéfice net ≥ 20 €.
Rouge = perte ou concurrence trop forte (jamais envoyé). Orange = bénéfice possible mais un élément manque.
Les volumes viennent d'un cache (data/base/volumes.json + bingo) ; les manquants sont demandés à DataForSEO
en UN seul appel par tour (≈ 0,09 $), seulement si le budget du jour garde une réserve pour le bingo de la nuit."""
import json
import os
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_VOL = os.path.join(RACINE, "data/base/volumes.json")
MARGE_MIN = 20
MARGE_ENVOI = 10   # sous 10 € de bénéfice, l'alerte n'est pas envoyée (comme le seuil de déclenchement des chasses)
VOLUME_MIN = 1000
RESERVE_BINGO_USD = 0.35  # bingo + hype de la nuit


def _lire(f, d):
    try:
        with open(f, encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError):
        return d


def cle(x):
    return (x.get("nom_produit") or x.get("titre") or "").strip().lower()[:80]


def _cache():
    vol = _lire(F_VOL, {})
    for b in _lire(os.path.join(RACINE, "data/bingo.json"), {}).get("meilleurs", []):
        if b.get("mot_cle") and b.get("recherches_mois") is not None:
            vol.setdefault(b["mot_cle"].lower(), {"v": b["recherches_mois"], "d": "bingo"})
    return vol


F_DERNIER = os.path.join(RACINE, "data/etat/volumes_alertes.json")
INTERVALLE_MIN = 120   # un appel groupé toutes les 2 heures au plus (≈ 12 appels/jour max, en pratique bien moins)


def _reserve():
    """La réserve ne sert qu'à garantir le bingo et la hype de la nuit : une fois faits aujourd'hui, plus de réserve."""
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hype = _lire(os.path.join(RACINE, "data/hype_telegram.json"), {}).get("maj", "")
    return 0 if hype[:10] == jour else RESERVE_BINGO_USD


def _intervalle_ok():
    d = _lire(F_DERNIER, {}).get("dernier")
    return not d or (datetime.now(timezone.utc) - datetime.fromisoformat(d)).total_seconds() >= INTERVALLE_MIN * 60


def _noter_appel():
    os.makedirs(os.path.dirname(F_DERNIER), exist_ok=True)
    json.dump({"dernier": datetime.now(timezone.utc).isoformat(timespec="minutes")}, open(F_DERNIER, "w"))


def completer_volumes(annonces):
    """Un appel DataForSEO pour tous les noms sans volume connu (si le budget le permet). Renvoie le cache."""
    vol = _cache()
    manquants = sorted({cle(x) for x in annonces if cle(x) and cle(x) not in vol})[:500]
    if manquants:
        try:
            from . import dataforseo
            if dataforseo.disponible(0.09 + _reserve()) and _intervalle_ok():
                res = dataforseo.volumes(manquants)
                _noter_appel()
                jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                for m in manquants:
                    r = res.get(m) or next((v for k, v in res.items() if k.lower() == m), None)
                    if res:  # appel réussi : un mot absent de la réponse = volume nul
                        vol[m] = {"v": (r or {}).get("volume_mensuel") or 0, "d": jour}
                if res:
                    propre = {k: v for k, v in vol.items() if v.get("d") != "bingo"}
                    os.makedirs(os.path.dirname(F_VOL), exist_ok=True)
                    json.dump(propre, open(F_VOL, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    return vol


def evaluer(x, vol=None):
    """Calcule les six éléments et le feu. Ne dépense rien (le volume vient du cache)."""
    vol = vol if vol is not None else _cache()
    k = x.get("keepa") or {}
    achat = x.get("cout_achat") or x.get("prix")
    pp = x.get("prix_plancher") or {}
    neufs = [(pp.get("prix_min"), pp.get("ou") or "comparateur", pp.get("lien")), (k.get("prix_neuf"), "Amazon", k.get("lien"))]
    neufs = [n for n in neufs if isinstance(n[0], (int, float)) and n[0] > 0]
    neuf_min, neuf_ou, neuf_lien = min(neufs, key=lambda n: n[0]) if neufs else (None, None, None)
    ecart = round((1 - achat / neuf_min) * 100) if achat and neuf_min else None
    vendeurs = x.get("vendeurs_amazon", k.get("nb_vendeurs_neuf"))
    v = (vol.get(cle(x)) or {}).get("v")
    # occasion : plus bas / plus haut vus (annonces réelles Vinted/Leboncoin + Amazon occasion)
    occ = []
    for site, r in (x.get("revente_reelle") or {}).items():
        if isinstance(r, dict):
            occ += [p for p in (r.get("min"), r.get("mediane"), r.get("max")) if isinstance(p, (int, float))]
    eo = (x.get("ebay") or {}).get("occasion") or {}
    occ += [p for p in (eo.get("min"), eo.get("max")) if isinstance(p, (int, float))]
    if vendeurs is None and isinstance(((x.get("ebay") or {}).get("neuf") or {}).get("nb"), int):
        vendeurs = x["ebay"]["neuf"]["nb"]  # secours : nombre d'annonces neuves sur eBay France
    if isinstance(k.get("occasion"), (int, float)):
        occ.append(k["occasion"])
    occ_bas, occ_haut = (min(occ), max(occ)) if occ else (None, None)
    # Recalculer les marges historiques, jamais faire confiance au cache d'avant audit.
    from .rentabilite import calculer
    from .validation import blocages
    regles = _lire(os.path.join(RACINE, "config/regles.json"), {})
    seuil_vert = regles.get("seuils", {}).get("marge_verte_min", MARGE_MIN)
    seuil_envoi = regles.get("seuils", {}).get("marge_nette_min", MARGE_ENVOI)
    canaux = []
    for c in x.get("canaux") or []:
        if not isinstance(c, dict) or achat is None:
            continue
        try:
            detail = calculer(c["prix_vente"], c["canal"], achat, regles)
        except (KeyError, ValueError, TypeError, ArithmeticError):
            continue
        canaux.append({**c, "marge_nette": detail["marge_nette"], "calcul_marge": detail})
    best = max(canaux, key=lambda c: c["marge_nette"], default=None)
    marge = best["marge_nette"] if best else None
    achat_max = round(marge + achat - seuil_vert, 2) if best and achat else None
    f = {"achat": achat, "neuf_min": neuf_min, "neuf_ou": neuf_ou, "neuf_lien": neuf_lien, "ecart_pct": ecart, "vendeurs": vendeurs, "volume": v,
         "occ_bas": occ_bas, "occ_haut": occ_haut, "ventes_30j": x.get("ventes_estimees_30j", k.get("ventes_estimees_30j")),
         "vendre_sur": best.get("canal") if best else None, "prix_vente": best.get("prix_vente") if best else None,
         "benefice": marge, "achat_max": achat_max, "manque": []}
    # ROUGE : on passe
    if marge is None or marge < seuil_envoi or (neuf_min and achat >= neuf_min):
        f["feu"], f["raison"] = "rouge", "bénéfice sous 10 €"
        return f
    if isinstance(vendeurs, int) and (vendeurs >= 10 or (vendeurs >= 5 and (ecart or 0) < 15)):
        f["feu"], f["raison"] = "rouge", f"concurrence trop forte ({vendeurs} vendeurs)"
        return f
    # VERT = l'affaire tient (règle de David, 05/11, cas Dyson V12s) : bénéfice ≥ 20 €, prix neuf France connu et
    # au moins 15 % au-dessus de notre achat, pas de signal contraire connu. Les données manquantes (concurrence,
    # volume, occasion) sont affichées « à compléter » mais ne bloquent plus le vert.
    f["a_completer"] = []
    f["manque"].extend(blocages(x))
    f["calcul_marge"] = best.get("calcul_marge") if best else None
    if marge < seuil_vert:
        f["manque"].append(f"bénéfice sous {seuil_vert} €")
    if neuf_min is None:
        f["manque"].append("prix neuf ailleurs inconnu")
    elif ecart is not None and ecart < 15:
        f["manque"].append(f"seulement {ecart} % sous le prix France")
    if occ_bas is not None and f["prix_vente"] and f["vendre_sur"] in ("vinted", "leboncoin", "facebook") and f["prix_vente"] > occ_haut * 1.1:
        f["manque"].append("revente au-dessus des prix d'occasion vus")
    if vendeurs is None:
        f["a_completer"].append("concurrence")
    if v is None:
        f["a_completer"].append("volume de recherche")
    elif v < 300:
        f["a_completer"].append(f"peu recherché sous ce nom exact ({v}/mois)")
    if occ_bas is None:
        f["a_completer"].append("prix d'occasion")
    f["feu"] = "vert" if not f["manque"] else "orange"
    f.update(probabilite_vente(x, f))
    return f


def _ventes_ebay(x):
    base = _lire(os.path.join(RACINE, "data/pc/ventes_ebay.json"), {})
    nom = (x.get("nom_produit") or "").strip().lower()
    for k, v in base.items():
        if k.strip().lower() == nom:
            return v
    return None


def probabilite_vente(x, f):
    """ESTIMATION (règles, pas encore calibrée sur nos ventes) de la probabilité de vendre en moins de 7 jours.
    Croise : ventes Amazon 30 j, dernières ventes réelles eBay (7 j / 30 j), recherches Google, concurrence, et notre prix
    face au prix médian réellement payé. Chaque signal présent ajoute ou retire des points ; renvoie aussi le détail."""
    import math
    pts, detail = 0.0, []
    a30 = f.get("ventes_30j")
    if isinstance(a30, (int, float)) and a30 > 0:
        pts += min(2.0, math.log10(a30 + 1))          # 10 ventes -> 1 ; 100 -> 2
        detail.append(f"Amazon {int(a30)}/mois")
    e = _ventes_ebay(x)
    if e:
        pts += min(1.5, (e.get("ventes_7j") or 0) / 4)  # 6 ventes eBay en 7 j -> plein
        detail.append(f"eBay {e.get('ventes_7j', 0)} vendus en 7 j")
        if e.get("prix_median") and f.get("prix_vente"):
            ratio = f["prix_vente"] / e["prix_median"]
            pts += 0.8 if ratio <= 0.9 else 0.3 if ratio <= 1.0 else -0.8 if ratio > 1.15 else 0
            detail.append(f"prix payé médian {e['prix_median']:.0f} €")
    v = f.get("volume")
    if isinstance(v, (int, float)) and v > 0:
        pts += min(1.5, math.log10(v) / 3)               # 1 000 -> 1 ; 30 000 -> 1,5
        detail.append(f"Google {int(v)}/mois")
    c = f.get("vendeurs")
    if isinstance(c, int):
        pts += 0.6 if c <= 4 else 0 if c <= 9 else -0.8
    if not detail:
        return {"proba_vente_7j": None, "proba_detail": []}
    niveau = "forts" if pts >= 3.5 else "moyens" if pts >= 2 else "faibles"
    return {"proba_vente_7j": None, "indicateurs_demande": niveau, "proba_detail": detail}
