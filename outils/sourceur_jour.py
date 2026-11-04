"""Fiches Sourceur pour les bingos du jour (Gemini + Google, quelques centimes). outil = sourceur_jour"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import sourceur
sourceur.jour(10)
subprocess.run([sys.executable, "saas/rapport_david.py"])
