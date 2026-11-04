"""Affiche le nom du passage (nuit/midi/soir) attendu pour ce créneau s'il n'a pas eu lieu aujourd'hui, sinon rien.
Créneaux (UTC) : nuit dès 03:45, midi dès 11:45, soir dès 16:45 (les horaires programmés sont 03:33 / 11:33 / 16:33 ;
GitHub en saute souvent : la veille suivante rattrape)."""
import datetime
import json

h = datetime.datetime.now(datetime.timezone.utc)
m = h.hour * 60 + h.minute
creneau = "soir" if m >= 16 * 60 + 45 else "midi" if m >= 11 * 60 + 45 else "nuit" if m >= 3 * 60 + 45 else ""
try:
    p = json.load(open("data/dernier_passage.json", encoding="utf-8"))
    jour_paris = (h + datetime.timedelta(hours=1)).strftime("%Y-%m-%d")
    deja = p.get("horodatage", "")[:10] == jour_paris and (p.get("passage") == creneau or (creneau == "nuit" and p.get("passage") == "europe"))
    # un passage plus tardif du même jour compte aussi (ex. soir fait -> midi n'est plus à rattraper)
    ordre = {"nuit": 0, "midi": 1, "soir": 2}
    if p.get("horodatage", "")[:10] == jour_paris and ordre.get(p.get("passage"), -1) >= ordre.get(creneau, 9):
        deja = True
except Exception:
    deja = False
print("" if (not creneau or deja) else creneau)
