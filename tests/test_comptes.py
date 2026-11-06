import json
import unittest
from unittest.mock import patch
from outils import controle_comptes as c


class ComptesTests(unittest.TestCase):
    def test_aucun_acces_aucun_appel(self):
        with patch.object(c, 'lire', side_effect=AssertionError('réseau interdit')):
            self.assertFalse(c.controler({})['autorise_activation'])

    def test_reponse_privee_non_reproduite(self):
        brut = {'login': 'PRIVE', 'token': 'SECRET', 'status_code': 20000, 'cost': 0,
                'tasks': [{'status_code': 20000, 'cost': 0, 'result': [{'login': 'PRIVE', 'money': {
                    'statistics': {'day': {'total_serp': .2, 'value': '2026-11-06'}}, 'balance': 40}}]}]}
        r = c.resumer_dataforseo(brut)
        self.assertTrue(r['compteur_journalier_disponible'])
        self.assertNotIn('PRIVE', json.dumps(r))
        self.assertNotIn('balance', json.dumps(r))
        self.assertFalse(r['autorise_activation'])

    def test_seules_les_deux_lectures_officielles(self):
        with patch.object(c, 'lire', side_effect=ValueError('SECRET')) as lire:
            r = c.controler({'DATAFORSEO_LOGIN': 'test', 'DATAFORSEO_PASSWORD': 'SECRET', 'APIFY_TOKEN': 'SECRET'})
        self.assertEqual([x.args[0] for x in lire.call_args_list], [
            'https://api.dataforseo.com/v3/appendix/user_data', 'https://api.apify.com/v2/users/me/limits'])
        self.assertNotIn('SECRET', json.dumps(r))
        self.assertEqual(r['apify']['statut'], 'lecture_impossible')

    def test_depassement_et_reponse_incomplete_ne_deverrouillent_pas(self):
        r = c.resumer_apify({'data': {'current': {'monthlyUsageUsd': 36}, 'limits': {'maxMonthlyUsageUsd': 35}}})
        self.assertTrue(r['plafond_fournisseur_atteint'])
        self.assertFalse(r['autorise_activation'])
        self.assertEqual(c.resumer_apify({})['statut'], 'compteur_inconnu')
        self.assertEqual(c.resumer_dataforseo({'status_code': 20000, 'cost': .1})['statut'], 'reponse_non_validee')
