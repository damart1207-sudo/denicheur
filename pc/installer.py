"""Crée (ou remplace) la tâche planifiée Windows « Denicheur collecteur » : toutes les heures, silencieuse (pythonw, pas de fenêtre).
À lancer une fois : python pc/installer.py      Pour l'enlever : schtasks /delete /tn "Denicheur collecteur" /f"""
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
script = os.path.join(RACINE, "pc", "collecteur.py")
pythonw = sys.executable.replace("python.exe", "pythonw.exe")
if not os.path.exists(pythonw):
    pythonw = sys.executable
cmd = ["schtasks", "/create", "/f", "/sc", "hourly", "/mo", "1", "/tn", "Denicheur collecteur",
       "/tr", f'"{pythonw}" "{script}"', "/st", "00:07"]
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout or r.stderr)
print("Tâche créée : le collecteur tourne toutes les heures (à h+07) tant que le PC est allumé." if r.returncode == 0 else "Échec : lance ce script dans un terminal ouvert « en tant qu'administrateur ».")
