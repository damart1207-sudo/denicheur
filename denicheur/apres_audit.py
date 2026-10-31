"""Après l'audit : recalcule le championnat et reconstruit la page du SaaS.

python -m denicheur.apres_audit
"""
import json
import os
import runpy

from . import championnat

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    cl = championnat.classement(os.path.join(RACINE, "data/championnat"), os.path.join(RACINE, "data/audits"))
    with open(os.path.join(RACINE, "data/classement.json"), "w", encoding="utf-8") as f:
        json.dump(cl, f, ensure_ascii=False, indent=1)
    print("Championnat recalculé :", {k: v.get("global", {}).get("points") for k, v in cl.items()})
    runpy.run_path(os.path.join(RACINE, "saas/construire.py"), run_name="__main__")


if __name__ == "__main__":
    main()
