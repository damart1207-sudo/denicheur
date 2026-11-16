"""Contre-exemples de détection et de budget, sans aucun fournisseur réel."""
import copy
import json
import subprocess
import sys
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from denicheur import arbitrage, keepa, moisson, veille

REGLES = json.loads((Path(__file__).resolve().parents[1] / 'config/regles.json').read_text())


class DetectionTests(unittest.TestCase):
    def annonce(self, prix=28.80):
        return {'id': 'keepa-B08HTF1HRG-warehouse', 'asin': 'B08HTF1HRG',
                'titre': 'Chernobyl Steelbook 4K', 'prix': prix, 'devise': 'EUR',
                'pays': 'FR', 'source': 'keepa-radar', 'lien': 'https://example.invalid'}

    def examiner(self, a, reference):
        with ExitStack() as stack:
            for cible, valeur in [('comparateurs.prix_plancher', None), ('base.noter_prix', None),
                    ('meme_produit', None), ('apify.prix_idealo', None), ('apify.revente_reelle', None),
                    ('demande.est_demande', None), ('equipe.canaux_de_vente', []), ('lecteur.lire_offre', None)]:
                stack.enter_context(patch('denicheur.veille.' + cible, return_value=valeur))
            stack.enter_context(patch.object(keepa, 'fiche', return_value=reference))
            recherche = stack.enter_context(patch.object(keepa, 'rechercher'))
            x = veille.examiner(a, a['titre'], datetime.now(timezone.utc), REGLES, set())
            recherche.assert_not_called()
            return x

    def test_comparateur_absent_asin_exact_garde(self):
        x = self.examiner(self.annonce(), {'asin': 'B08HTF1HRG', 'titre': 'Chernobyl Steelbook 4K', 'prix_neuf': 268})
        self.assertEqual(x['statut'], 'a_verifier')
        self.assertEqual(x['prix_plancher']['prix_min'], 268)

    def test_baisse_historique_sans_ecart_actuel_rejetee(self):
        self.assertIsNone(self.examiner(self.annonce(70.99),
            {'asin': 'B08HTF1HRG', 'titre': 'Chernobyl Steelbook 4K', 'prix_neuf': 70.99}))

    def test_panne_reference_differee(self):
        a = self.annonce()
        self.assertIsNone(self.examiner(a, None))
        self.assertTrue(a['_a_reessayer'])

    def test_changement_prix_revu_avant_delai(self):
        a = self.annonce()
        now = datetime.now(timezone.utc)
        vus = {a['id']: {'empreinte': veille.empreinte(a), 'prochain': (now + timedelta(hours=24)).isoformat()}}
        self.assertFalse(veille.a_revoir(a, vus, now))
        a['prix'] = 20
        self.assertTrue(veille.a_revoir(a, vus, now))

    def test_delai_passe_revu(self):
        a = self.annonce()
        now = datetime.now(timezone.utc)
        vus = {a['id']: {'empreinte': veille.empreinte(a), 'prochain': (now - timedelta(seconds=1)).isoformat()}}
        self.assertTrue(veille.a_revoir(a, vus, now))

    def test_asin_lien_amazon_sans_inventer_identite(self):
        a = {'lien': 'https://www.amazon.fr/dp/B08HTF1HRG?tag=test'}
        veille.identifier_asin(a)
        self.assertEqual(a['asin'], 'B08HTF1HRG')
        b = {'lien': 'https://example.invalid/dp/B08HTF1HRG'}
        veille.identifier_asin(b)
        self.assertNotIn('asin', b)

    def test_radar_et_arbitrage_reutilises_sans_reseau(self):
        with patch.object(moisson, 'annonces_radar', return_value=[self.annonce()]) as radar, \
             patch.object(arbitrage, 'annonces_arbitrage', return_value=[{'id': 'arb'}]) as arb:
            self.assertEqual(len(veille.annonces_keepa()), 2)
            radar.assert_called_once_with(maxi=12)
            arb.assert_called_once_with(maxi=8)


class LotsTests(unittest.TestCase):
    def setUp(self):
        avant = copy.deepcopy(moisson._jetons)
        self.addCleanup(lambda: moisson._jetons.update(avant))
        moisson._jetons.update(restants=206, depenses=0)
        reserve = patch('denicheur.classements.reserve_keepa', return_value=0)
        reserve.start()
        self.addCleanup(reserve.stop)

    def test_206_jetons_autorisent_28_fiches_et_7_comparaisons(self):
        self.assertEqual(moisson.taille_lot(100, 2, {'jetons_jour': 0}), 28)
        self.assertEqual(moisson.taille_lot(40, 8, {'jetons_jour': 0}), 7)

    def test_plafond_jour_et_reserve_priment(self):
        self.assertEqual(moisson.taille_lot(40, 8, {'jetons_jour': 24000}), 0)
        moisson._jetons['restants'] = 150
        self.assertEqual(moisson.taille_lot(40, 8, {'jetons_jour': 0}), 0)

    def test_etagere_reprend_file_sans_nouvelle_requete(self):
        etat = {'jetons_jour': 0, 'tours': 1,
                'etagere_attente': {'categorie': 'Informatique', 'asins': [str(i) for i in range(100)]}}
        with patch.object(moisson, 'categories_fr', return_value=[(1, 'Informatique')]), \
             patch.object(moisson, '_appel') as appel, \
             patch.object(moisson, 'fiches', return_value=[{'asin': '0'}]) as fiches, \
             patch.object(moisson, '_garder', return_value=1):
            self.assertEqual(moisson.etagere(etat, nb_cats=1), 1)
            appel.assert_not_called()
            self.assertEqual(len(fiches.call_args.args[0]), 28)
            self.assertEqual(len(etat['etagere_attente']['asins']), 72)

    def test_lancement_module_partage_compteur(self):
        code = '''import runpy, sys
from unittest.mock import patch
from denicheur import keepa
with patch.object(keepa, "cle", return_value=""):
    runpy.run_module("denicheur.moisson", run_name="__main__", alter_sys=True)
from denicheur import moisson, arbitrage
assert arbitrage.moisson is moisson
moisson._jetons["depenses"] = 123
assert arbitrage.moisson._jetons["depenses"] == 123
'''
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rotation_recoltes_evite_famine(self):
        for tour, premier in [(0, 'arbitrage'), (1, 'etagere'), (2, 'hype')]:
            ordre = []
            with patch.object(keepa, 'cle', return_value='FAUX'), \
                 patch.object(moisson, '_etat', return_value={'jetons_jour': 0, 'tours': tour}), \
                 patch.object(moisson, '_ecrire'), patch.object(moisson, 'radar', return_value=0), \
                 patch('denicheur.recherches_prix.tour', return_value=0), \
                 patch.object(arbitrage, 'tour', side_effect=lambda e: ordre.append('arbitrage') or 0), \
                 patch.object(moisson, 'etagere', side_effect=lambda e: ordre.append('etagere') or 0), \
                 patch.object(moisson, 'hype', side_effect=lambda e: ordre.append('hype') or 0):
                moisson.tour()
            self.assertEqual(ordre[0], premier)
