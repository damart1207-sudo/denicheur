"""Lance le bingo du jour seul (Gemini mots-clés + DataForSEO ≈ 0,10 $ + eBay gratuit), puis reconstruit les rapports.
Lancement : workflow « Dénicheur », outil = bingo_jour"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import bingo  # noqa: E402

bingo.jour()
from denicheur import sourceur  # noqa: E402
sourceur.jour()
subprocess.run([sys.executable, "saas/rapport_hype.py"])
subprocess.run([sys.executable, "saas/rapport_david.py"])
