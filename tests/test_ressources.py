"""Régressions économiques : fournisseurs simulés, aucune connexion réelle."""
import ast
import copy
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from denicheur import apify, arbitrage, budget, keepa, moisson
from denicheur.rentabilite import depuis_audit
from saas import rapport_david

ROOT = Path(__file__).resolve().parents[1]
REGLES = json.loads((ROOT / 'config/regles.json').read_text())


def reponse(d):
    class Reponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(d).encode()
    return Reponse()


class MargesTests(unittest.TestCase):
    def test_adidas_ancien_net_refuse(self):
        r = depuis_audit({'cout_achat': 28.41}, {'prix_revente_verifie': 40,
            'plateforme_verifiee': 'vinted', 'marge_nette_verifiee': 11.59}, REGLES)
        self.assertEqual(r['marge'], 3.23)

    def test_timex_conservee(self):
        r = depuis_audit({'cout_achat': 41.06}, {'prix_revente_verifie': 65,
            'plateforme_verifiee': 'vinted', 'marge_nette_verifiee': 12.2}, REGLES)
        self.assertEqual(r['marge'], 12.23)

    def test_canal_absent_ou_inconnu_ne_reutilise_pas_marge_ia(self):
        for canal in [None, 'inconnu']:
            r = depuis_audit({'cout_achat': 28.41}, {'prix_revente_verifie': 40,
                'plateforme_verifiee': canal, 'marge_nette_verifiee': 999}, REGLES)
            self.assertIsNone(r['marge'])
            self.assertTrue(r['blocage_marge'])

    def test_prix_zero_non_remplace_par_ancien_prix(self):
        r = depuis_audit({'cout_achat': 28.41, 'prix_revente_prudent': 100},
            {'prix_revente_verifie': 0, 'canal': 'vinted'}, REGLES)
        self.assertEqual(r['marge'], -31.41)

    def test_cout_absent_ou_invalide(self):
        for cout in [None, -1, float('nan'), float('inf')]:
            self.assertIsNone(depuis_audit({'cout_achat': cout},
                {'prix_revente_verifie': 40, 'canal': 'vinted'}, REGLES)['marge'])

    def test_configuration_respectee_sans_modifier_entree(self):
        regles = copy.deepcopy(REGLES)
        regles['fiscalite'].update(cotisations=0, versement_liberatoire=0,
            formation_professionnelle=0, provision_incident_eur=0)
        c, v = {'cout_achat': 28.41}, {'prix_revente_verifie': 40, 'canal': 'vinted'}
        avant = copy.deepcopy((c, v))
        self.assertEqual(depuis_audit(c, v, regles)['marge'], 11.59)
        self.assertEqual((c, v), avant)

    def test_rapport_affiche_3_23_et_rouge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data/audits').mkdir(parents=True)
            (root / 'config').mkdir()
            (root / 'config/regles.json').write_text(json.dumps(REGLES))
            (root / 'data/dernier_passage.json').write_text(json.dumps({
                'horodatage': 'test', 'candidats': [{'id': 'adidas', 'cout_achat': 28.41,
                    'feu': 'orange', 'plateforme_revente': 'vinted'}]}))
            (root / 'data/audits/test.json').write_text(json.dumps({'verdicts': [{
                'id': 'adidas', 'verdict': 'bon', 'prix_revente_verifie': 40,
                'plateforme_verifiee': 'vinted', 'marge_nette_verifiee': 11.59}]}))
            with patch.object(rapport_david, 'RACINE', tmp), redirect_stdout(io.StringIO()):
                rapport_david.construire()
            html = (root / 'data/rapport_david.html').read_text()
            d = json.JSONDecoder().raw_decode(html.split('const D = ', 1)[1])[0]
            self.assertEqual(d['affaires'][0]['marge'], 3.23)
            self.assertEqual(d['affaires'][0]['feu'], 'rouge')


class KeepaTests(unittest.TestCase):
    def setUp(self):
        self.sauve = copy.deepcopy(moisson._jetons)
        moisson._jetons.update(restants=500, depenses=0)
        self.reserve = patch('denicheur.classements.reserve_keepa', return_value=0)
        self.reserve.start()
        self.addCleanup(self.reserve.stop)
        self.addCleanup(lambda: (moisson._jetons.clear(), moisson._jetons.update(self.sauve)))

    def appel(self, d, cout=40):
        with patch.object(keepa, 'cle', return_value='FAUSSE_CLE'), \
             patch.object(keepa, '_dernier', [0]), \
             patch('urllib.request.urlopen', return_value=reponse(d)):
            return moisson._appel('product', {}, etat={'jetons_jour': 0}, cout_max=cout)

    def test_tokens_fournisseur_malgre_refill(self):
        self.appel({'tokensLeft': 490, 'tokensConsumed': 30})
        self.assertEqual(moisson._jetons['depenses'], 30)

    def test_zero_reel_accepte(self):
        self.appel({'tokensLeft': 500, 'tokensConsumed': 0})
        self.assertEqual(moisson._jetons['depenses'], 0)

    def test_sans_mesure_reservation_conservatrice(self):
        self.appel({'tokensLeft': 490})
        self.assertEqual(moisson._jetons['depenses'], 40)

    def test_reserve_blocage_avant_reseau(self):
        moisson._jetons['restants'] = 155
        with patch('urllib.request.urlopen') as net:
            with self.assertRaises(moisson.BudgetKeepaInsuffisant):
                moisson.fiches(['A', 'B', 'C'], etat={'jetons_jour': 0})
            net.assert_not_called()

    def test_plafond_jour_blocage_avant_reseau(self):
        with patch('urllib.request.urlopen') as net:
            with self.assertRaises(moisson.BudgetKeepaInsuffisant):
                moisson.fiches(['A'], etat={'jetons_jour': moisson.JETONS_JOUR_MAX})
            net.assert_not_called()

    def test_timeout_conserve_cout_maximal(self):
        with patch('urllib.request.urlopen', side_effect=TimeoutError()), patch.object(keepa, 'cle', return_value='FAUSSE_CLE'):
            with self.assertRaises(TimeoutError):
                moisson._appel('product', {}, etat={'jetons_jour': 0}, cout_max=40)
        self.assertEqual(moisson._jetons['depenses'], 40)
        self.assertEqual(moisson._jetons['restants'], 460)

    def test_depassement_cout_stoppe_lots_suivants(self):
        self.appel({'tokensLeft': 450, 'tokensConsumed': 50}, cout=40)
        self.assertEqual(moisson._jetons['restants'], 0)

    def test_solde_manquant_arrete_moisson(self):
        self.appel({'tokensConsumed': 1})
        self.assertEqual(moisson._jetons['restants'], 0)

    def test_arbitrage_incomplet_pas_marque_vu(self):
        with patch.object(arbitrage, 'file_attente', return_value=['A']), \
             patch.object(arbitrage, '_lire', return_value={}), \
             patch.object(arbitrage, 'comparer', side_effect=moisson.BudgetKeepaInsuffisant()), \
             patch.object(arbitrage, '_ecrire') as ecrire, patch('denicheur.sante.noter'):
            self.assertEqual(arbitrage.tour({'jetons_jour': 0}, par_tour=1), 0)
            ecrire.assert_not_called()


class ApifyTests(unittest.TestCase):
    def test_ancien_compteur_tour_ignore(self):
        with patch.dict(os.environ, {'APIFY_TOKEN': 'FAUX_JETON'}), \
             patch.object(apify, 'depense_du_jour', return_value=0), \
             patch.object(apify, 'depense_reelle', return_value=5), \
             patch.object(apify, '_reel', {}), \
             patch.object(apify, '_budget', return_value={'depense_estimee_usd': 10, 'depense_ce_tour': 1000}):
            self.assertTrue(apify.disponible())

    def test_erreur_usage_fournisseur_bloque(self):
        with patch.dict(os.environ, {'APIFY_TOKEN': 'FAUX_JETON'}), \
             patch.object(apify, 'depense_du_jour', return_value=0), \
             patch.object(apify, 'depense_reelle', return_value=None):
            self.assertFalse(apify.disponible())

    def test_sonde_refusee_par_meme_registre(self):
        with patch.object(apify, 'disponible', return_value=True), \
             patch.object(apify, '_budget', return_value={}), \
             patch.object(apify, 'depense_reelle', return_value=0), \
             patch.object(apify, 'depense_du_jour', return_value=0), \
             patch.object(budget, 'reserver', return_value=None) as reserve, \
             patch('urllib.request.urlopen') as net:
            self.assertIsNone(apify.lancer_test('sonde', 'acteur~test', {}))
            self.assertEqual(reserve.call_args.args[0:2], ('apify', .05))
            self.assertEqual(reserve.call_args.args[3], apify.BUDGET_MOIS_USD)
            net.assert_not_called()

    def test_estimation_ne_libere_pas_reservation(self):
        with patch.object(apify, 'disponible', return_value=True), \
             patch.object(apify, '_budget', return_value={}), \
             patch.object(apify, 'depense_reelle', return_value=0), \
             patch.object(apify, 'depense_du_jour', return_value=0), \
             patch.object(budget, 'reserver', return_value='reservation'), \
             patch.object(budget, 'rapprocher') as rapprocher, \
             patch.object(apify, '_noter'), patch('denicheur.journal.noter'), \
             patch.dict(os.environ, {'APIFY_TOKEN': 'FAUX_JETON'}), \
             patch('urllib.request.urlopen', return_value=reponse([])):
            self.assertEqual(apify.lancer('tiktok_top', {}), [])
            self.assertEqual(rapprocher.call_args.args[2], apify.ROBOTS['tiktok_top'][1])

    def test_trois_sondes_n_ont_plus_de_post_direct(self):
        for nom in ['test_apify_reel.py', 'test_demande.py', 'test_demande2.py']:
            code = (ROOT / 'outils' / nom).read_text()
            self.assertIn('.lancer_test(', code)
            self.assertNotIn('/run-sync-get-dataset-items', code)


if __name__ == '__main__':
    unittest.main()
