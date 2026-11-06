import unittest
from unittest.mock import patch
from denicheur import comparateurs, keepa


class IdentificationTests(unittest.TestCase):
    def test_suffixe_msi_et_asus_ne_peut_etre_ignore(self):
        for a, b in [('MSI PRO A620M-E', 'MSI PRO A620M-B'), ('ASUS X870-I', 'ASUS X870-F')]:
            self.assertFalse(comparateurs.correspond(b, a))

    def test_reference_identique_et_typographie(self):
        self.assertTrue(comparateurs.correspond('Carte mère MSI PRO A620M-E DDR5', 'MSI PRO A620M-E'))
        self.assertTrue(comparateurs.correspond('Carte mère MSI PRO A620M E DDR5', 'MSI PRO A620M-E'))
        self.assertFalse(comparateurs.correspond('MSI PRO A620M-E-WIFI', 'MSI PRO A620M-E'))
        self.assertFalse(comparateurs.correspond('Téléphone 17e', 'Téléphone 17'))
        self.assertFalse(comparateurs.correspond('Produit quelconque', ''))

    def test_keepa_selectionne_identifiant_exact_pas_premier_resultat(self):
        produits = [{'asin': 'MAUVAIS', 'eanList': ['9999999999999']},
                    {'asin': 'CORRECT', 'eanList': ['4711377093804']}]
        with patch.object(keepa, 'disponible', return_value=True), patch.object(keepa, '_budget', return_value={}), \
             patch.object(keepa, '_noter'), patch.object(keepa, '_lire', return_value={'products': produits}):
            self.assertEqual(keepa.fiche(ean='4711377093804')['asin'], 'CORRECT')
            self.assertIsNone(keepa.fiche(ean='1234567890123'))
            self.assertEqual(keepa.fiche(asin='CORRECT')['asin'], 'CORRECT')
            self.assertIsNone(keepa.fiche(asin='ABSENT'))

    def test_keepa_recherche_ne_reutilise_pas_autre_modele(self):
        produits = [{'title': 'MSI PRO A620M-B', 'asin': 'MAUVAIS', 'stats': {}}]
        with patch.object(keepa, 'disponible', return_value=True), patch.object(keepa, '_budget', return_value={}), \
             patch.object(keepa, '_noter'), patch.object(keepa, '_lire_url', return_value={'products': produits}):
            self.assertIsNone(keepa.rechercher('MSI PRO A620M-E'))

    def test_gtin_rempli_de_zeros_et_ambiguite(self):
        p = {'asin': 'CORRECT', 'eanList': ['4711377093804']}
        with patch.object(keepa, 'disponible', return_value=True), patch.object(keepa, '_budget', return_value={}), \
             patch.object(keepa, '_noter'), patch.object(keepa, '_lire', return_value={'products': [p]}) as lire:
            self.assertEqual(keepa.fiche(ean='04711377093804')['asin'], 'CORRECT')
            lire.return_value = {'products': [p, {**p, 'asin': 'AUTRE'}]}
            self.assertIsNone(keepa.fiche(ean='4711377093804'))

    def test_liste_identifiants_malformee_refusee(self):
        with patch.object(keepa, 'disponible', return_value=True), patch.object(keepa, '_budget', return_value={}), \
             patch.object(keepa, '_noter'), patch.object(keepa, '_lire', return_value={'products': [None, {'eanList': '4711377093804'}]}):
            self.assertIsNone(keepa.fiche(ean='4711377093804'))
