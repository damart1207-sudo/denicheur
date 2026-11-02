"""Carnet de santé des dénicheurs : chaque tour réussi, chaque erreur, chaque étape en panne.
Claude le lit chaque heure et prévient David dès qu'un problème dure.

python -m denicheur.sante echec "message"   (appelé par le workflow quand un tour plante)
"""
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(RACINE, "data", "sante.json")


def _lire():
    try:
        return json.load(open(F, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tours_ok": 0, "tours_echec": 0, "dernier_ok": None, "evenements": []}


def _ecrire(d):
    os.makedirs(os.path.dirname(F), exist_ok=True)
    d["evenements"] = d["evenements"][-300:]
    json.dump(d, open(F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _heure():
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M")


def noter(niveau, etape, message):
    """niveau : 'erreur' (étape en panne, le tour continue) ou 'echec' (tour entier perdu)."""
    d = _lire()
    d["evenements"].append({"heure": _heure(), "niveau": niveau, "etape": etape, "message": str(message)[:300]})
    if niveau == "echec":
        d["tours_echec"] += 1
    _ecrire(d)


def tour_ok(resume):
    d = _lire()
    d["tours_ok"] += 1
    d["dernier_ok"] = _heure()
    d["dernier_resume"] = resume
    _ecrire(d)


def protege(etape, fonction, *args, defaut=None, **kw):
    """Exécute une étape ; si elle plante, on le note et on continue avec une valeur par défaut."""
    try:
        return fonction(*args, **kw)
    except Exception as e:
        noter("erreur", etape, f"{type(e).__name__}: {e} | {traceback.format_exc(limit=2)[-200:]}")
        return defaut


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "echec":
        noter("echec", "tour", " ".join(sys.argv[2:]))
