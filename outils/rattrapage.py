"""Affiche le nom du passage (nuit/midi/soir) attendu pour ce créneau s'il n'a pas eu lieu aujourd'hui, sinon rien.
Utilisé par le workflow (rattrapage quand GitHub saute un horaire programmé)."""
import datetime
import json

h = datetime.datetime.utcnow()
creneau = "nuit" if 4 <= h.hour <= 9 else "midi" if 12 <= h.hour <= 15 else "soir" if 17 <= h.hour <= 23 else ""
try:
    p = json.load(open("data/dernier_passage.json", encoding="utf-8"))
    fait = p.get("horodatage", "")[:10] == (h + datetime.timedelta(hours=1)).strftime("%Y-%m-%d") and (p.get("passage") == creneau or (creneau == "nuit" and p.get("passage") == "europe"))
except Exception:
    fait = False
print("" if (not creneau or fait) else creneau)
