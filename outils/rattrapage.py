"""Affiche le nom du passage (nuit/midi/soir) attendu pour ce créneau s'il n'a pas eu lieu aujourd'hui, sinon rien.
Utilisé par le workflow (rattrapage quand GitHub saute un horaire programmé).

Règles (04/11/2026, après trois rattrapages de nuit lancés à la suite et tous coupés) :
- un passage compte comme fait dès qu'un fichier data/passages/<date>_<heure>_<passage>.json du jour existe
  (data/dernier_passage.json ne suffit pas : un passage « midi » lancé à la main l'écrase et faisait croire que la nuit manquait) ;
- un rattrapage n'est tenté qu'UNE fois par créneau et par jour (marque data/etat/rattrapage.json), même s'il a échoué :
  mieux vaut un passage manqué qu'une veille bloquée pendant des heures.
- écrit par le workflow : `python outils/rattrapage.py marquer <passage>` pose la marque.
"""
import datetime
import glob
import json
import os
import sys
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_MARQUE = os.path.join(RACINE, "data", "etat", "rattrapage.json")
EQUIVALENTS = {"nuit": ("nuit", "europe"), "midi": ("midi",), "soir": ("soir",)}


ORDRE = {"nuit": 0, "midi": 1, "soir": 2}


def creneau_actuel(h_utc=None):
    """Créneaux (UTC) : nuit dès 03:45, midi dès 11:45, soir dès 16:45 (horaires programmés 03:33 / 11:33 / 16:33, souvent sautés)."""
    h = h_utc or datetime.datetime.now(datetime.timezone.utc)
    m = h.hour * 60 + h.minute
    return "soir" if m >= 16 * 60 + 45 else "midi" if m >= 11 * 60 + 45 else "nuit" if m >= 3 * 60 + 45 else ""


def passage_fait(creneau, jour_paris):
    """Vrai si ce créneau, ou un créneau plus tardif du même jour, a laissé un fichier dans data/passages (ou dernier_passage.json)."""
    valables = [p for c, ps in EQUIVALENTS.items() if ORDRE.get(c, 9) >= ORDRE.get(creneau, 0) for p in ps]
    for p in valables:
        if glob.glob(os.path.join(RACINE, "data", "passages", f"{jour_paris}_*_{p}.json")):
            return True
    try:
        d = json.load(open(os.path.join(RACINE, "data", "dernier_passage.json"), encoding="utf-8"))
        return d.get("horodatage", "")[:10] == jour_paris and d.get("passage") in valables
    except Exception:
        return False


def _marques():
    try:
        return json.load(open(F_MARQUE, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def marquer(creneau, jour_paris):
    m = _marques()
    m = {k: v for k, v in m.items() if k.startswith(jour_paris)}  # on ne garde que le jour courant
    m[f"{jour_paris}:{creneau}"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(F_MARQUE), exist_ok=True)
    json.dump(m, open(F_MARQUE, "w", encoding="utf-8"), indent=1)


def manquant():
    h = datetime.datetime.now(datetime.timezone.utc)
    creneau = creneau_actuel(h)
    jour = h.astimezone(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d")
    if not creneau or passage_fait(creneau, jour) or f"{jour}:{creneau}" in _marques():
        return ""
    return creneau


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "marquer":
        marquer(sys.argv[2], datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d"))
    else:
        print(manquant())
