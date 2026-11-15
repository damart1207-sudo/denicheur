"""Lance uniquement les régressions de ce lot, avec toute connexion interdite."""
import json
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

tentatives = []
def interdit(*args, **kwargs):
    tentatives.append('connexion interdite')
    raise AssertionError('Les tests ne doivent jamais utiliser le réseau')

suite = unittest.TestSuite()
for nom in ['test_budget.py', 'test_audit.py', 'test_ressources.py']:
    suite.addTests(unittest.defaultTestLoader.discover('tests', pattern=nom))
with patch.object(socket.socket, 'connect', interdit), patch.object(socket, 'create_connection', interdit):
    resultat = unittest.TextTestRunner(verbosity=2).run(suite)
bilan = {'tests': resultat.testsRun, 'erreurs': len(resultat.errors),
         'echecs': len(resultat.failures), 'connexions_reseau': len(tentatives)}
Path('resultats_tests.json').write_text(json.dumps(bilan, indent=2))
raise SystemExit(0 if resultat.wasSuccessful() and not tentatives else 1)
