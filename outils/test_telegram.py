"""Test Telegram : envoie un message à David. Lancement : workflow « Dénicheur », outil = test_telegram"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import telegram  # noqa: E402

print("secrets présents :", telegram.pret())
ok = telegram.envoyer("✅ Rebifftout Dénicheur : le test Telegram fonctionne. Les alertes et rapports arriveront ici.")
print("message envoyé :", ok)
sys.exit(0 if ok else 1)
