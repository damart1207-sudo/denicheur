"""CHASSEUR PC (dénicheur C, sur le PC de David, accord du 04/11) : annonces de particuliers SOUS-COTÉES sur Vinted et Leboncoin
pour les produits que l'on sait revendre (étagère, bingos, arbitrage, liste de chasse d'Amigo).
Trois filets :
 1. sous-coté : annonces les plus récentes, prix ≤ SEUIL × prix de référence (prix payé d'occasion : eBay vendus, Vinted ;
    sinon prix neuf Keepa × 0,6) ;
 2. annonces INVISIBLES : variantes mal orthographiées du nom (« iphon », « switsh », espaces, sans accent), lots ;
 3. vendeur PRESSÉ : « urgent », « déménagement », « à débarrasser », « cause départ », « ne sert plus », « prix négociable ».
Rythme humain : RECHERCHES_MAX recherches par tour, pauses aléatoires, navigateur connecté (même profil que le collecteur).
-> data/pc/chasse.json (lu par la veille du cloud : alertes Telegram, cartes signées Chasseur)
python pc/chasseur.py        (un tour ; la tâche planifiée « Denicheur chasseur » le lance toutes les 20 minutes)"""
import hashlib
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pc.collecteur import PROFIL, pousser  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_SORTIE = os.path.join(RACINE, "data", "pc", "chasse.json")
F_VUS = os.path.join(RACINE, "data", "pc", "chasse_vus.json")
SEUIL = 0.65            # sous-coté : ≤ 65 % du prix de référence
RECHERCHES_MAX = 40     # par tour (rythme humain)
PRESSE = re.compile(r"urgent|d[ée]m[ée]nagement|d[ée]barrass|cause d[ée]part|ne sert plus|n[ée]gociable|vite|rapide|cadeau|double emploi|jamais servi|neuf jamais", re.I)


def _lire(f, defaut):
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaut


def _ascii(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def variantes(nom):
    """Le nom tel qu'on le tape bien, puis mal : sans accents, espaces en plus/en moins, lettres doublées, finales coupées."""
    n = _ascii(nom).strip()
    out = [n]
    mots = n.split()
    if len(mots) >= 2:
        out.append("".join(mots[:2]) + " " + " ".join(mots[2:]))        # « airpods pro » -> « airpodspro »
        out.append(re.sub(r"(\D)(\d)", r"\1 \2", n))                     # « v11 » -> « v 11 »
    out.append(re.sub(r"ph", "f", n))                                    # iphone -> ifone (rare mais réel)
    out.append(re.sub(r"(.)\1", r"\1", n))                               # lettres doublées retirées
    out.append(n[:-1] if len(n) > 6 else n)                              # dernière lettre coupée (« iphon »)
    out.append(n + " lot")
    return list(dict.fromkeys([v for v in out if len(v) >= 4]))


def cibles():
    """Produits à chasser : liste de chasse d'Amigo (bingos, hype, idealo) + étagère + arbitrage, avec un prix de référence."""
    cib = {}
    base = _lire(os.path.join(RACINE, "data/base/keepa_index.json"), {})
    for b in _lire(os.path.join(RACINE, "data/bingo.json"), {}).get("bingos", [])[:30]:
        ref = b.get("prix_neuf_france") or b.get("prix")
        if ref:
            cib[b["mot_cle"]] = {"nom": b["mot_cle"], "ref_neuf": ref, "ref_occasion": None, "origine": "bingo"}
    for a in _lire(os.path.join(RACINE, "data/arbitrage.json"), {}).get("ecarts", [])[:30]:
        nom = (a.get("titre") or "")[:50]
        if nom and a.get("prix_fr"):
            cib.setdefault(nom, {"nom": nom, "ref_neuf": a["prix_fr"], "ref_occasion": None, "origine": "arbitrage"})
    for x in _lire(os.path.join(RACINE, "data/demande.json"), {}).get("liste", [])[:20]:
        if x.get("pays") == "FR":
            cib.setdefault(x["recherche"], {"nom": x["recherche"], "ref_neuf": None, "ref_occasion": None, "origine": "idealo"})
    for k, r in sorted(base.items(), key=lambda kv: -(kv[1].get("ch30") or 0))[:40]:
        if k.endswith(":FR") and r.get("t") and r.get("neuf"):
            nom = re.split(r"[,(|\[\-–:]", r["t"], maxsplit=1)[0].strip()[:50]
            cib.setdefault(nom, {"nom": nom, "ref_neuf": r["neuf"], "ref_occasion": r.get("occ"), "origine": "etagere"})
    return list(cib.values())


def reference(c):
    return c.get("ref_occasion") or (c["ref_neuf"] * 0.6 if c.get("ref_neuf") else None)


def chercher_vinted(page, q):
    """Vinted : page catalogue, données JSON de la page (annonces les plus récentes)."""
    page.goto("https://www.vinted.fr/catalog?order=newest_first&search_text=" + urllib.parse.quote(q), wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1500 + random.randint(0, 1500))
    h = page.content()
    out = []
    for m in re.finditer(r'"id":(\d+),"title":"((?:[^"\\]|\\.)*)".{0,400}?"price":\{"amount":"([\d.]+)"', h):
        out.append({"titre": m.group(2).encode().decode("unicode_escape", "ignore"), "prix": float(m.group(3)),
                    "lien": f"https://www.vinted.fr/items/{m.group(1)}", "site": "vinted"})
    if not out:  # secours : cartes HTML
        for m in re.finditer(r'href="(https://www\.vinted\.fr/items/\d+[^"]*)"[^>]*title="([^"]+)".{0,800}?(\d+[,.]\d{2})\s?€', h, re.S):
            out.append({"titre": m.group(2), "prix": float(m.group(3).replace(",", ".")), "lien": m.group(1), "site": "vinted"})
    return out[:40]


def chercher_leboncoin(page, q):
    """Leboncoin : recherche triée par date, données JSON __NEXT_DATA__ de la page."""
    page.goto("https://www.leboncoin.fr/recherche?text=" + urllib.parse.quote(q) + "&sort=time&order=desc", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500 + random.randint(0, 2500))
    h = page.content()
    out = []
    i = h.find('"ads":[')
    if i > 0:
        for m in re.finditer(r'"list_id":(\d+),.{0,2500}?"subject":"((?:[^"\\]|\\.)*)".{0,3000}?"price":\[(\d+)\]', h[i:i + 400000], re.S):
            out.append({"titre": m.group(2).encode().decode("unicode_escape", "ignore"), "prix": float(m.group(3)),
                        "lien": f"https://www.leboncoin.fr/ad/x/{m.group(1)}", "site": "leboncoin"})
    return out[:40]


def tour():
    from playwright.sync_api import sync_playwright
    cib = cibles()
    if not cib:
        print("chasseur : aucune cible (bingo/arbitrage/étagère vides)")
        return
    random.shuffle(cib)
    vus = _lire(F_VUS, {})
    trouves, etat = [], {"recherches": 0, "annonces_lues": 0}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFIL, headless=True, locale="fr-FR", viewport={"width": 1366, "height": 900},
                                                   args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        n = 0
        for c in cib:
            ref = reference(c)
            for q in variantes(c["nom"])[:3]:
                if n >= RECHERCHES_MAX:
                    break
                for site, f in (("vinted", chercher_vinted), ("leboncoin", chercher_leboncoin)):
                    if n >= RECHERCHES_MAX:
                        break
                    try:
                        ann = f(page, q)
                    except Exception as e:
                        ann = []
                        etat.setdefault("erreurs", []).append(f"{site} {q}: {type(e).__name__}")
                    n += 1
                    etat["annonces_lues"] += len(ann)
                    for a in ann:
                        ident = hashlib.sha1(a["lien"].encode()).hexdigest()[:10]
                        if ident in vus:
                            continue
                        mots_q = set(_ascii(c["nom"]).split())
                        mots_t = set(_ascii(a["titre"]).split())
                        if len(mots_q & mots_t) < max(1, len(mots_q) - 1) and q == variantes(c["nom"])[0]:
                            continue  # pas le bon produit
                        presse = bool(PRESSE.search(a["titre"]))
                        sous_cote = bool(ref and a["prix"] <= ref * SEUIL and a["prix"] >= (ref or 0) * 0.15)
                        invisible = q != variantes(c["nom"])[0]
                        if not (sous_cote or presse or invisible):
                            continue
                        vus[ident] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        trouves.append({"id": ident, "titre": a["titre"][:160], "prix": a["prix"], "lien": a["lien"], "site": site,
                                        "produit": c["nom"], "origine": c["origine"], "recherche": q, "ref_neuf": c.get("ref_neuf"),
                                        "ref_occasion": c.get("ref_occasion"), "reference": ref, "ecart_pct": round((1 - a["prix"] / ref) * 100) if ref else None,
                                        "signaux": [s for s, v in (("sous-coté", sous_cote), ("vendeur pressé", presse), ("annonce invisible", invisible)) if v],
                                        "vu": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "denicheur": "C"})
                    time.sleep(2 + random.random() * 4)
        ctx.close()
    etat["recherches"] = n
    anciens = [x for x in _lire(F_SORTIE, {}).get("annonces", []) if x.get("vu", "") >= (datetime.now(timezone.utc).strftime("%Y-%m-%d"))]
    trouves.sort(key=lambda x: -(x.get("ecart_pct") or 0))
    os.makedirs(os.path.dirname(F_SORTIE), exist_ok=True)
    json.dump({"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"), "etat": etat, "cibles": len(cib), "annonces": (anciens + trouves)[-800:]},
              open(F_SORTIE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    limite = (datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    json.dump({k: v for k, v in vus.items() if v >= limite[:8] + "01"}, open(F_VUS, "w", encoding="utf-8"))
    print(f"chasseur : {n} recherches, {etat['annonces_lues']} annonces lues, {len(trouves)} retenues")
    for t in trouves[:8]:
        print(" ", t["site"], t["prix"], "€", t["signaux"], t["titre"][:60], "| réf", t["reference"])
    return trouves


if __name__ == "__main__":
    tour()
    print(pousser())
