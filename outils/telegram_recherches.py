"""Envoie tout de suite sur Telegram les produits les plus recherchés. Lancement : outil = telegram_recherches"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import telegram  # noqa: E402
ok = telegram.plus_recherches()
print("envoyé :", ok)
sys.exit(0 if ok else 1)
