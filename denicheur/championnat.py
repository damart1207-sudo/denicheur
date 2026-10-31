"""Championnat des IA : chaque proposition est enregistrée, puis notée grâce à l'audit de Claude.

Barème : +3 si l'affaire est validée à l'audit, -1 si elle est rejetée, 0 si non auditée.
Classement global et par domaine.
"""
import glob
import json
import os


def enregistrer(dossier, date, passage, tous_choix):
    os.makedirs(dossier, exist_ok=True)
    with open(os.path.join(dossier, "propositions.jsonl"), "a", encoding="utf-8") as f:
        for c in tous_choix:
            f.write(json.dumps({"date": date, "passage": passage, "agent": c["agent"], "id": c["id"],
                                "domaine": c["domaine"]}, ensure_ascii=False) + "\n")


def classement(dossier_champ, dossier_audits):
    verdicts = {}
    for chemin in sorted(glob.glob(os.path.join(dossier_audits, "*.json"))):
        try:
            with open(chemin, encoding="utf-8") as f:
                audit = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for i in audit.get("valides", []):
            verdicts[str(i)] = 1
        for r in audit.get("rejetes", []):
            verdicts[str(r.get("id") if isinstance(r, dict) else r)] = -1
    stats, deja = {}, set()
    chemin = os.path.join(dossier_champ, "propositions.jsonl")
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                try:
                    p = json.loads(ligne)
                except json.JSONDecodeError:
                    continue
                if (p["agent"], p["id"]) in deja:
                    continue
                deja.add((p["agent"], p["id"]))
                for cle in (("global",), ("domaine", p["domaine"])):
                    s = stats.setdefault(p["agent"], {}).setdefault("/".join(cle), {"proposees": 0, "validees": 0, "rejetees": 0, "points": 0})
                    s["proposees"] += 1
                    v = verdicts.get(p["id"])
                    if v == 1:
                        s["validees"] += 1
                        s["points"] += 3
                    elif v == -1:
                        s["rejetees"] += 1
                        s["points"] -= 1
    return stats
