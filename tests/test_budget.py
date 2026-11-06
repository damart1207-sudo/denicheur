import base64
import copy
import io
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from denicheur import budget, dataforseo, apify


class BudgetTests(unittest.TestCase):
    def test_concurrence_ne_depasse_pas_plafond(self):
        with tempfile.TemporaryDirectory() as tmp:
            back = budget.Local(Path(tmp) / 'budget.json')
            def demande(_):
                return budget.reserver('test', .1, 1, 10, backend=back)
            with ThreadPoolExecutor(max_workers=20) as pool:
                res = list(pool.map(demande, range(40)))
            self.assertEqual(sum(r is not None for r in res), 10)
            s = json.loads(back.chemin.read_text())['services']['test']
            self.assertEqual(list(s['jours'].values()), [1_000_000])

    def test_crash_conserve_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'budget.json'
            self.assertIsNotNone(budget.reserver('x', .7, 1, 1, backend=budget.Local(path)))
            self.assertIsNone(budget.reserver('x', .4, 1, 1, backend=budget.Local(path)))

    def test_rapprochement_zero_et_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = budget.Local(Path(tmp) / 'budget.json')
            ident = budget.reserver('x', .7, 1, 1, backend=b)
            budget.rapprocher('x', ident, 0, backend=b)
            budget.rapprocher('x', ident, 0, backend=b)
            self.assertIsNotNone(budget.reserver('x', 1, 1, 1, backend=b))

    def test_depassement_tarif_bloque_suivants(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = budget.Local(Path(tmp) / 'budget.json')
            ident = budget.reserver('x', .1, 1, 1, backend=b)
            budget.rapprocher('x', ident, .2, backend=b)
            self.assertIsNone(budget.reserver('x', .01, 1, 1, backend=b))

    def test_migration_et_categorie(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = budget.Local(Path(tmp) / 'budget.json')
            kw = dict(categorie='A', plafond_categorie=.5, deja_jour=.7,
                      deja_mois=.7, deja_categorie=.4, backend=b)
            self.assertIsNotNone(budget.reserver('x', .1, 1, 1, **kw))
            self.assertIsNone(budget.reserver('x', .1, 1, 1, **kw))

    def test_registre_corrompu_bloque(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'budget.json'
            p.write_text('fichier coupé')
            with self.assertRaises(budget.Indisponible):
                budget.reserver('x', .1, 1, 1, backend=budget.Local(p))

    def test_migration_bloque_toute_nouvelle_depense(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'budget.json'
            p.write_text(json.dumps({'migration_en_cours': True, 'services': {}}))
            with self.assertRaises(budget.Indisponible):
                budget.reserver('x', .1, 1, 1, backend=budget.Local(p))

    def test_actions_sans_jeton_ne_replie_pas_sur_disque(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'BUDGET_GITHUB_TOKEN': ''}):
            with self.assertRaises(budget.Indisponible):
                budget.stockage()

    def test_cas_github_reessaie_sans_perdre_reservation_concurrente(self):
        g = budget.GitHub('owner/repo', 'FAUX_JETON_TEST')
        calls = []
        def api(route, data=None, method=None):
            calls.append((route, data, method))
            if method == 'PUT':
                if len([x for x in calls if x[2] == 'PUT']) == 1:
                    raise HTTPError(route, 409, 'conflit', {}, None)
                return {}
            # Le second GET contient déjà la dépense d'un autre runner.
            used = 900_000 if len([x for x in calls if x[2] == 'PUT']) else 0
            from datetime import datetime, timezone
            jour = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            etat = {'version': 1, 'services': {'x': {'jours': {jour: used}, 'mois': {jour[:7]: used},
                    'categories': {}, 'reserves': {}}}}
            return {'sha': 'revision', 'content': base64.b64encode(json.dumps(etat).encode()).decode()}
        with patch.object(g, '_api', side_effect=api), patch.object(budget.time, 'sleep'):
            self.assertIsNone(budget.reserver('x', .2, 1, 1, backend=g))
        puts = [x for x in calls if x[2] == 'PUT']
        etat = json.loads(base64.b64decode(puts[-1][1]['content']))
        self.assertFalse(etat['services']['x']['reserves'])

    def test_put_incertain_n_autorise_pas_la_depense(self):
        g = budget.GitHub('owner/repo', 'FAUX_JETON_TEST')
        def api(route, data=None, method=None):
            if method == 'PUT':
                raise TimeoutError()
            etat = {'version': 1, 'services': {'x': {'jours': {}, 'mois': {}, 'categories': {}, 'reserves': {}}}}
            return {'sha': 'revision', 'content': base64.b64encode(json.dumps(etat).encode()).decode()}
        with patch.object(g, '_api', side_effect=api):
            with self.assertRaises(budget.Indisponible):
                budget.reserver('x', .1, 1, 1, backend=g)

    def test_registre_github_absent_ne_recree_pas_les_compteurs(self):
        g = budget.GitHub('owner/repo', 'FAUX_JETON_TEST')
        with patch.object(g, '_api', side_effect=HTTPError('url', 404, 'absent', {}, None)) as api:
            with self.assertRaisesRegex(budget.Indisponible, 'restauration requise'):
                budget.reserver('x', .1, 1, 1, backend=g)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.args, ('/contents/registre-budgets.json?ref=budget-api',))

    def test_registre_github_vide_ou_version_inconnue_bloque(self):
        g = budget.GitHub('owner/repo', 'FAUX_JETON_TEST')
        for etat in [{}, {'version': 1, 'services': {}}, {'version': 2, 'services': {'x': {}}}]:
            contenu = base64.b64encode(json.dumps(etat).encode()).decode()
            with self.subTest(etat=etat), patch.object(g, '_api', return_value={'sha': 'revision', 'content': contenu}) as api:
                with self.assertRaises(budget.Indisponible):
                    budget.reserver('x', .1, 1, 1, backend=g)
                self.assertEqual(api.call_count, 1)

    def test_dataforseo_arrete_avant_appel_si_budget_epuise(self):
        with patch.object(dataforseo, '_auth', return_value='AUTH_TEST'), \
             patch.object(dataforseo, '_budget', return_value={'depense_usd': 0}), \
             patch.object(budget, 'reserver', return_value=None), \
             patch('urllib.request.urlopen', side_effect=AssertionError('appel payant interdit')):
            self.assertEqual(dataforseo._poster('test', [], .09), [])

    def test_dataforseo_timeout_garde_reservation(self):
        with patch.object(dataforseo, '_auth', return_value='AUTH_TEST'), \
             patch.object(dataforseo, '_budget', return_value={'depense_usd': 0}), \
             patch.object(budget, 'reserver', return_value='reserve'), \
             patch.object(budget, 'rapprocher') as rap, \
             patch('urllib.request.urlopen', side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):
                dataforseo._poster('test', [], .09)
            rap.assert_not_called()

    def test_apify_ne_lance_pas_si_reservation_refusee(self):
        with patch.object(apify, 'disponible', return_value=True), \
             patch.object(apify, '_budget', return_value={}), \
             patch.object(apify, 'depense_reelle', return_value=0), \
             patch.object(apify, 'depense_du_jour', return_value=0), \
             patch.object(budget, 'reserver', return_value=None), \
             patch('urllib.request.urlopen', side_effect=AssertionError('appel payant interdit')):
            self.assertIsNone(apify.lancer('idealo', {}))


if __name__ == '__main__':
    unittest.main()
