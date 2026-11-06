import copy
import unittest
from saas.pilote import examiner, prix_minimum, construire
from test_audit import candidat, REGLES
from denicheur.rentabilite import calculer


class PiloteTests(unittest.TestCase):
    def test_seuil_atteint_objectif_sur_trois_canaux(self):
        for canal in ('leboncoin', 'ebay', 'rebifftout'):
            p = prix_minimum(78.98, canal, REGLES)
            self.assertGreaterEqual(calculer(p, canal, 78.98, REGLES)['marge_nette'], 20)

    def test_ancienne_marge_et_validation_ignorées(self):
        x = candidat()
        x['canaux'] = [{'canal': 'leboncoin', 'prix_vente': 30, 'marge_nette': 999}]
        avant = copy.deepcopy(x)
        r = examiner(x, REGLES)
        self.assertLess(r['marge'], 0)
        self.assertEqual(r['statut'], 'À écarter selon hypothèses')
        self.assertEqual(x, avant)

    def test_benefice_estime_ne_donne_pas_ordre_achat(self):
        x = candidat()
        x['canaux'] = [{'canal': 'leboncoin', 'prix_vente': 100}]
        r = examiner(x, REGLES)
        self.assertEqual(r['statut'], 'À vérifier')
        self.assertTrue(any('ventes conclues' in s for s in r['raisons']))

    def test_modele_keepa_contradictoire_signale(self):
        x = {**candidat(), 'nom_produit': 'MSI PRO A620M-E', 'keepa': {'titre': 'MSI PRO A620M-B'}}
        self.assertTrue(any('Keepa' in s for s in examiner(x, REGLES)['raisons']))

    def test_titre_externe_ne_peut_injecter_script(self):
        x = {**candidat(), 'nom_produit': '</script><script>alert(1)</script>'}
        rendu = construire([x], REGLES)
        self.assertNotIn('</script><script>alert(1)', rendu)
        self.assertIn('\\u003c/script', rendu)

    def test_devises_etrangeres_pas_traitees_comme_euros(self):
        r = examiner({**candidat(), 'devise': 'GBP'}, REGLES)
        self.assertIsNone(r['calcul'])
        self.assertIsNone(r['minimum'])
