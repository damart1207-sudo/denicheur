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
VOLUME_MIN = 1000
RESERVE_BINGO_USD = 0.35  # bingo + hype de la nuit


def _lire(f, d):
    try:
        return json.load(open(f, encoding="utf-8"))
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


def completer_volumes(annonces):
    """Un appel DataForSEO pour tous les noms sans volume connu (si le budget le permet). Renvoie le cache."""
    vol = _cache()
    manquants = sorted({cle(x) for x in annonces if cle(x) and cle(x) not in vol})[:500]
    if manquants:
        try:
            from . import dataforseo
            if dataforseo.disponible(0.09 + RESERVE_BINGO_USD):
                res = dataforseo.volumes(manquants)
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
    neufs = [(pp.get("prix_min"), pp.get("ou") or "comparateur"), (k.get("prix_neuf"), "Amazon")]
    neufs = [(p, o) for p, o in neufs if isinstance(p, (int, float)) and p > 0]
    neuf_min, neuf_ou = min(neufs) if neufs else (None, None)
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
    canaux = [c for c in (x.get("canaux") or []) if isinstance(c, dict) and isinstance(c.get("marge_nette"), (int, float))]
    best = max(canaux, key=lambda c: c["marge_nette"], default=None)
    marge = best["marge_nette"] if best else None
    achat_max = round(marge + achat - MARGE_MIN, 2) if best and achat else None
    f = {"achat": achat, "neuf_min": neuf_min, "neuf_ou": neuf_ou, "ecart_pct": ecart, "vendeurs": vendeurs, "volume": v,
         "occ_bas": occ_bas, "occ_haut": occ_haut, "ventes_30j": x.get("ventes_estimees_30j", k.get("ventes_estimees_30j")),
         "vendre_sur": best.get("canal") if best else None, "prix_vente": best.get("prix_vente") if best else None,
         "benefice": marge, "achat_max": achat_max, "manque": []}
    # ROUGE : on passe
    if marge is None or marge <= 0 or (neuf_min and achat >= neuf_min):
        f["feu"], f["raison"] = "rouge", "pas de bénéfice"
        return f
    if isinstance(vendeurs, int) and (vendeurs >= 10 or (vendeurs >= 5 and (ecart or 0) < 15)):
        f["feu"], f["raison"] = "rouge", f"concurrence trop forte ({vendeurs} vendeurs)"
        return f
    # VERT seulement si tout se croise
    if marge < MARGE_MIN:
        f["manque"].append(f"bénéfice sous {MARGE_MIN} €")
    if vendeurs is None:
        f["manque"].append("concurrence inconnue")
    if v is None:
        f["manque"].append("volume de recherche inconnu")
    elif v < VOLUME_MIN:
        f["manque"].append(f"peu recherché ({v}/mois)")
    if occ_bas is None:
        f["manque"].append("prix d'occasion inconnus")
    elif f["prix_vente"] and occ_bas and f["vendre_sur"] in ("vinted", "leboncoin", "facebook") and f["prix_vente"] > occ_haut * 1.1:
        f["manque"].append("revente au-dessus des prix d'occasion vus")
    if neuf_min is None:
        f["manque"].append("prix neuf ailleurs inconnu")
    f["feu"] = "vert" if not f["manque"] else "orange"
    return f
