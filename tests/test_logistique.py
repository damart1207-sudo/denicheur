import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from denicheur import logistique, verif_prix, validation, equipe
from test_audit import URL, candidat, produit, offre, html, REGLES


def detail():
    return {'prix': 30, 'offre': offre(30,
        priceSpecification={'price': 30, 'priceCurrency': 'EUR', 'valueAddedTaxIncluded': True},
        shippingDetails={'shippingDestination': {'addressCountry': 'FR'},
                         'shippingOrigin': {'addressCountry': 'FR'},
                         'shippingRate': {'@type': 'MonetaryAmount', 'currency': 'EUR', 'value': 5}})}


class LogistiqueTests(unittest.TestCase):
    def test_total_reel_remplace_port_estime(self):
        x = candidat()
        p = logistique.depuis_offre(detail(), URL)
        logistique.appliquer(x, p)
        self.assertEqual(x['cout_achat'], 35)
        self.assertEqual(equipe.cout_achat(x, REGLES), 35)
        self.assertEqual(validation.blocages(x), [])

    def test_port_zero_est_un_prix(self):
        d = detail()
        d['offre']['shippingDetails']['shippingRate']['value'] = 0
        self.assertEqual(logistique.depuis_offre(d, URL)['total'], 30)

    def test_origine_absente_ou_hors_ue_total_inconnu(self):
        for pays in [None, 'CN', 'UK']:
            d = detail()
            d['offre']['shippingDetails']['shippingOrigin']['addressCountry'] = pays
            p = logistique.depuis_offre(d, URL)
            self.assertIsNone(p['total'])
            x = candidat()
            e = logistique.appliquer(x, p)
            self.assertTrue(e['livraison'])
            self.assertIsNone(e['total'])

    def test_tva_absente_ou_contradictoire(self):
        for spec in [{}, {'valueAddedTaxIncluded': False},
                     [{'valueAddedTaxIncluded': True}, {'valueAddedTaxIncluded': False}]]:
            d = detail()
            d['offre']['priceSpecification'] = spec
            self.assertIsNone(logistique.depuis_offre(d, URL)['total'])

    def test_tva_autre_prix_non_reutilisee(self):
        d = detail()
        d['offre']['priceSpecification']['price'] = 5
        self.assertIsNone(logistique.depuis_offre(d, URL)['total'])

    def test_destinations_etrangeres_et_regions_refusees(self):
        for r in [{'addressCountry': 'DE'}, {'addressCountry': 'FR', 'postalCode': '75001'},
                  {'addressCountry': 'FR', 'addressRegion': 'Paris'}]:
            d = detail()
            d['offre']['shippingDetails']['shippingDestination'] = r
            self.assertIsNone(logistique.depuis_offre(d, URL))

    def test_frais_conditionnels_ou_inconnus_refuses(self):
        for r in [{'value': 5, 'currency': 'USD'}, {'currency': 'EUR', 'minValue': 0, 'maxValue': 5},
                  {'value': -1, 'currency': 'EUR'}, {'value': float('nan'), 'currency': 'EUR'},
                  {'value': 0, 'currency': 'EUR', '@type': 'ShippingRateSettings'}]:
            d = detail()
            d['offre']['shippingDetails']['shippingRate'] = r
            self.assertIsNone(logistique.depuis_offre(d, URL))

    def test_tarifs_differents_ambigus(self):
        d = detail()
        s = d['offre']['shippingDetails']
        autre = copy.deepcopy(s)
        autre['shippingRate']['value'] = 10
        d['offre']['shippingDetails'] = [s, autre]
        self.assertIsNone(logistique.depuis_offre(d, URL))

    def test_exclusion_explicite_et_abonnement_refuses(self):
        d = detail()
        d['offre']['shippingDetails']['doesNotShip'] = True
        self.assertIsNone(logistique.depuis_offre(d, URL))
        d = detail()
        d['offre']['validForMemberTier'] = 'Prime'
        self.assertIsNone(logistique.depuis_offre(d, URL))

    def test_drapeaux_seuls_ne_suffisent_pas(self):
        x = candidat()
        del x['preuve_livraison']
        self.assertTrue(x['livraison_fr_confirmee'])
        self.assertFalse(logistique.etat(x)['livraison'])
        self.assertTrue(validation.blocages(x))

    def test_preuve_expiree_ou_autre_variante_refusee(self):
        for champ, valeur in [('verifie_le', (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()),
                              ('lien', URL.replace('noir','blanc')), ('total', 5), ('prix_article', 10)]:
            x = candidat()
            x['preuve_livraison'][champ] = valeur
            self.assertIsNone(logistique.etat(x)['total'])
            self.assertTrue(validation.blocages(x))

    def test_cout_modifie_sans_preuve_refuse(self):
        x = candidat()
        x['cout_achat'] = 1
        self.assertTrue(validation.blocages(x))

    def test_cout_transmis_par_controle_marchand(self):
        d = detail()
        h = html(produit(offers=d['offre']))
        class Reponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return URL
            def read(self, *args): return h.encode()
        x = candidat()
        with patch('urllib.request.urlopen', return_value=Reponse()):
            controle = verif_prix.controler(x)
        self.assertEqual(controle['statut'], 'ok')
        self.assertEqual(controle['preuve_livraison']['total'], 35)
        x['controle_prix'] = controle
        logistique.appliquer(x, controle['preuve_livraison'])
        self.assertEqual(validation.blocages(x), [])

    def test_recu_pc_transmet_la_logistique(self):
        x = candidat()
        x['preuve_prix'] = {'lien': URL, 'verifie_le': datetime.now(timezone.utc).isoformat(),
                           'devise': 'EUR', 'disponibilite': 'InStock', 'identite_confirmee': True,
                           'prix_page': 30, 'preuve_livraison': logistique.depuis_offre(detail(), URL)}
        with patch('urllib.request.urlopen', side_effect=AssertionError('pas de réseau')):
            self.assertEqual(verif_prix.controler(x)['preuve_livraison']['total'], 35)

    def test_devise_non_euro_n_est_pas_corrigee_comme_euro(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('pas de réseau')):
            self.assertEqual(verif_prix.controler({**candidat(),'devise':'GBP'})['statut'], 'inconnu')

    def test_url_commune_ne_masque_pas_un_gtin_different(self):
        h = html(produit(gtin13='1234567890123'))
        self.assertIsNone(verif_prix.prix_officiel(h, URL, ['9999999999999']))

    def test_preuve_malformee_ne_crashe_pas(self):
        self.assertIsNone(logistique.etat({**candidat(), 'preuve_livraison': []})['total'])
        x = candidat()
        x['preuve_livraison']['pays_expedition'] = ['FR']
        self.assertIsNone(logistique.etat(x)['total'])
