"""Construit la page du prototype (saas/index.html) à partir du dernier passage et de son audit.

python saas/construire.py
"""
import json
import os

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(rel, defaut=None):
    try:
        with open(os.path.join(RACINE, rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return defaut


def main():
    passage = lire("data/dernier_passage.json", {})
    classement = lire("data/classement.json", {})
    audit = lire(f"data/audits/{passage.get('horodatage', '')}.json") or {}
    verdicts = {v["id"]: v for v in audit.get("verdicts", [])}
    affaires = []
    for c in passage.get("candidats", []):
        a = {k: c.get(k) for k in ("id", "titre", "prix", "devise", "marchand", "lien", "pays", "domaine",
                                   "plateforme_revente", "prix_revente_estime", "cout_achat", "marge_nette",
                                   "rentabilite", "demande", "concurrence", "agents", "mode", "score", "erreur_prix",
                                   "verification", "marge_verifiee", "rentabilite_verifiee", "passe_verif")}
        a["audit"] = verdicts.get(c["id"], {"verdict": "attente"})
        affaires.append(a)
    donnees = {
        "date_affichee": passage.get("date_affichee"),
        "nb_annonces": passage.get("nb_annonces"),
        "nb_tries": passage.get("nb_tries"),
        "sources": passage.get("sources", {}),
        "agents": passage.get("agents", {}),
        "classement": classement,
        "affaires": affaires,
        "audit_fait": bool(audit),
        "audit_resume": audit.get("resume"),
    }
    with open(os.path.join(RACINE, "saas/modele.html"), encoding="utf-8") as f:
        modele = f.read()
    js = json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/")
    page = modele.replace("/*DONNEES*/null/*FIN*/", js)
    with open(os.path.join(RACINE, "saas/index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"saas/index.html : {len(affaires)} affaires, audit {'fait' if audit else 'en attente'}")


if __name__ == "__main__":
    main()
