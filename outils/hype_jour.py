"""Envoie tout de suite la hype étrangère du jour sur Telegram (≈ 0,09 $ DataForSEO + Gemini quelques centimes).
Lancement : outil = hype_jour"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import hype_jour  # noqa: E402
n = hype_jour.jour()
print("produits envoyés :", n)
sys.exit(0 if n else 1)
