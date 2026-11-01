"""Construit la page du SaaS (saas/index.html) à partir de TOUS les passages, audits et du championnat.

python saas/construire.py
"""
import glob
from datetime import datetime, timedelta, timezone
import json
import os

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAMPS = ("id", "titre", "prix", "devise", "marchand", "lien", "pays", "source", "temperature", "domaine",
          "plateforme_revente", "prix_revente_estime", "cout_achat", "marge_nette", "rentabilite", "demande",
          "concurrence", "consensus", "agents", "mode", "score", "erreur_prix", "raisons",
          "verification", "ebay", "prix_revente_prudent", "marge_verifiee", "rentabilite_verifiee", "passe_verif",
          "nom_produit", "rapport_demande", "rapport_concurrence", "prix_plancher", "canaux")


def lire(chemin, defaut=None):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return defaut


def rapport_recherches():
    """Rapport « Recherches et coûts » sur 10 et 30 jours, à partir de data/journal/ et data/alertes.json."""
    import sys
    sys.path.insert(0, RACINE)
    from denicheur import journal
    alertes = lire(os.path.join(RACINE, "data/alertes.json"), []) or []
    ok = [a for a in alertes if a.get("statut") in ("valide", "bon")]
    out = {}
    for jours in (10, 30):
        lignes = journal.lire(jours)
        def agreger(cle):
            g = {}
            for l in lignes:
                k = cle(l)
                if not k:
                    continue
                x = g.setdefault(k, {"cle": k, "recherches": 0, "cout_usd": 0.0, "resultats": 0, "alertes": 0, "validees": 0})
                for c in ("recherches", "resultats", "alertes"):
                    x[c] += l.get(c, 0)
                x["cout_usd"] = round(x["cout_usd"] + l.get("cout_usd", 0), 4)
            return g
        par_den, par_src = agreger(lambda l: l["denicheur"]), agreger(lambda l: l["source"])
        par_cat = agreger(lambda l: l["categorie"] if l["source"].startswith("flux:") else None)
        par_cible = agreger(lambda l: l["cible"] if l["source"].startswith("apify:") else None)
        for a in ok:
            t = a.get("trouve_le", "")
            if t and t[:10] < (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%d"):
                continue
            for g, k in ((par_den, a.get("denicheur") or "A"), (par_src, "flux:" + (a.get("source") or "?")),
                         (par_cat, (a.get("categorie") or "?")[:60]), (par_cible, a.get("nom_produit"))):
                if k in g:
                    g[k]["validees"] += 1
        tri = lambda g: sorted(g.values(), key=lambda x: (-x["cout_usd"], -x["resultats"]))
        out[f"j{jours}"] = {"denicheurs": tri(par_den), "sources": tri(par_src), "categories": tri(par_cat)[:60],
                            "cibles": tri(par_cible)[:60]}
    dm = lire(os.path.join(RACINE, "data/demande.json"), {}) or {}
    out["demande"] = {"maj": dm.get("maj"), "top": dm.get("liste", [])[:40], "chasse": dm.get("chasse_resultats", []),
                      "chasse_maj": dm.get("chasse_maj")}
    out["alertes"] = sorted(alertes, key=lambda a: a.get("trouve_le", ""), reverse=True)[:40]
    out["budget"] = lire(os.path.join(RACINE, "data/etat/apify_budget.json"), {})
    return out


def main():
    audits = {}
    for f in glob.glob(os.path.join(RACINE, "data/audits/*.json")):
        a = lire(f)
        if a:
            audits[a.get("horodatage") or os.path.basename(f)[:-5]] = a
    verdicts_globaux = {}
    for h in sorted(audits):
        for v in audits[h].get("verdicts", []):
            verdicts_globaux[v["id"]] = {**v, "audit_du": h}

    passages, affaires = [], {}
    for f in sorted(glob.glob(os.path.join(RACINE, "data/passages/*.json"))):
        p = lire(f)
        if not p or p.get("test"):
            continue
        h = p["horodatage"]
        passages.append({
            "horodatage": h, "passage": p["passage"], "date_affichee": p["date_affichee"],
            "nb_annonces": p["nb_annonces"], "nb_nouvelles": p.get("nb_nouvelles"), "nb_tries": p["nb_tries"],
            "nb_candidats": len(p.get("candidats", [])),
            "sources": {k: {"ok": v["ok"], "nb": v["nb"]} for k, v in p["sources"].items()},
            "agents": {k: {"appels": min(v["appels"], 99), "reussites": v.get("reussites", 0), "choix": v["choix"],
                           "remplace": v.get("remplace")} for k, v in p["agents"].items()},
            "verification": p.get("verification"),
            "audite": h in audits, "audit_resume": (audits.get(h) or {}).get("resume"),
        })
        for c in p.get("candidats", []):
            a = {k: c.get(k) for k in CHAMPS}
            a["passage"] = h
            a["audit"] = verdicts_globaux.get(c["id"], {"verdict": "attente"})
            affaires[c["id"]] = a  # la version la plus récente l'emporte

    donnees = {
        "genere": passages[-1]["date_affichee"] if passages else None,
        "passages": passages,
        "affaires": sorted(affaires.values(), key=lambda a: a["passage"], reverse=True),
        "recherches": rapport_recherches(),
        "classement": lire(os.path.join(RACINE, "data/classement.json"), {}),
        "regles": lire(os.path.join(RACINE, "config/regles.json"), {}),
        "equipe": {k: {"nom": v["nom"], "marque": v["marque"]}
                   for k, v in (lire(os.path.join(RACINE, "config/equipe.json"), {}).get("agents") or {}).items()},
        "roles": {k: v for k, v in (lire(os.path.join(RACINE, "config/equipe.json"), {}) or {}).items()
                  if k in ("trieur", "analystes", "verificateur", "remplacants")},
    }
    with open(os.path.join(RACINE, "saas/modele.html"), encoding="utf-8") as f:
        modele = f.read()
    js = json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(RACINE, "saas/index.html"), "w", encoding="utf-8") as f:
        f.write(modele.replace("/*DONNEES*/null/*FIN*/", js))
    try:
        import runpy
        runpy.run_path(os.path.join(RACINE, "saas/construire_site.py"), run_name="__main__")
    except Exception as ex:
        print("site public non construit :", ex)
    print(f"saas/index.html : {len(passages)} passages, {len(affaires)} affaires, {len(audits)} audit(s)")


if __name__ == "__main__":
    main()
