"""Régressions hors réseau : calculs, prix parasites, preuves et publication."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from denicheur import equipe, fiche, meme_produit, verif_prix, validation, telegram
from denicheur.rentabilite import calculer
from saas import construire_site

REGLES = json.loads((Path(__file__).resolve().parents[1] / 'config/regles.json').read_text())
URL = 'https://marchand.example/produit?couleur=noir'
NOW = datetime.now(timezone.utc).isoformat()


def offre(price=100, **kw):
    return {'@type': 'Offer', 'price': price, 'priceCurrency': 'EUR',
            'availability': 'https://schema.org/InStock', **kw}


def produit(url=URL, **kw):
    return {'@type': 'Product', 'url': url, 'offers': offre(), **kw}


def html(obj):
    return '<script type="application/ld+json">' + json.dumps(obj) + '</script>'


def candidat():
    return {'id': 'test', 'titre': 'Modèle noir', 'nom_produit': 'Modèle noir', 'prix': 30,
            'cout_achat': 30, 'devise': 'EUR', 'pays': 'FR', 'lien': URL,
            'prix_plancher': {'prix_min': 100, 'ou': 'comparateur'},
            'controle_prix': {'statut': 'ok', 'prix_page': 30, 'lien': URL, 'verifie_le': NOW},
            'meme_produit': {'meme': True}, 'livraison_fr_confirmee': True,
            'cout_total_confirme': True,
            'canaux': [{'canal': 'rebifftout', 'prix_vente': 90, 'marge_nette': 999}],
            'statut': 'valide', 'verifie_le': NOW}


class RentabiliteTests(unittest.TestCase):
    def test_charges_provision_et_paiement(self):
        d = calculer(100, 'rebifftout', 65, REGLES)
        self.assertEqual(d['prelevements'], 13.4)
        self.assertEqual(d['frais_canal'], 1.75)
        self.assertEqual(d['marge_nette'], 16.85)
        self.assertEqual(equipe.marge_nette(100, 'rebifftout', 65, REGLES), 16.85)

    def test_quinze_pourcent_ne_suffisent_pas(self):
        self.assertLess(calculer(100, 'rebifftout', 85, REGLES)['marge_nette'], 0)

    def test_marge_invalide_refusee(self):
        for v in [-1, float('inf'), float('nan')]:
            with self.subTest(v=v), self.assertRaises(ValueError):
                calculer(v, 'rebifftout', 10, REGLES)
        with self.assertRaises(KeyError):
            calculer(100, 'inconnu', 20, REGLES)

    def test_taux_configurables(self):
        r = copy.deepcopy(REGLES)
        r['fiscalite'].update(cotisations=0, versement_liberatoire=0,
                             formation_professionnelle=0, provision_incident_eur=0)
        self.assertEqual(calculer(100, 'rebifftout', 65, r)['marge_nette'], 33.25)

    def test_ancienne_marge_recalculee(self):
        x = candidat()
        x['cout_achat'] = 85
        f = fiche.evaluer(x, {})
        self.assertEqual(f['feu'], 'rouge')
        self.assertLess(f['benefice'], 0)


class PrixTests(unittest.TestCase):
    def test_produit_principal_selectionne(self):
        h = html([produit('https://marchand.example/autre', offers=offre(5)), produit()])
        self.assertEqual(verif_prix.prix_officiel(h, URL), 100)
        self.assertIsNone(verif_prix.prix_officiel(h))

    def test_recommandation_unique_refusee(self):
        self.assertIsNone(verif_prix.prix_officiel(html(produit('https://marchand.example/autre')), URL))

    def test_offre_epuisee_ignoree(self):
        h = html(produit(offers=[offre(10, availability='https://schema.org/OutOfStock'), offre(100)]))
        self.assertEqual(verif_prix.prix_officiel(h, URL), 100)

    def test_prix_script_sans_produit_refuse(self):
        self.assertIsNone(verif_prix.prix_officiel('<script>{"recommendation":{"price":9.99}}</script>', URL))

    def test_devise_stock_et_agregats(self):
        for o in [offre(priceCurrency='USD'), offre(availability=''),
                  offre(**{'@type': 'AggregateOffer'}), offre(float('nan'))]:
            with self.subTest(o=o):
                self.assertIsNone(verif_prix.prix_officiel(html(produit(offers=o)), URL))

    def test_variante_et_multi_vendeurs_refuses(self):
        self.assertIsNone(verif_prix.prix_officiel(html(produit(url=URL.replace('noir', 'blanc'))), URL))
        self.assertIsNone(verif_prix.prix_officiel(html(produit(offers=[offre(50), offre(100)])), URL))

    def test_canonique_et_graph(self):
        p = produit()
        del p['url']
        h = '<link rel="canonical" href="' + URL + '">' + html({'@graph': [p]})
        self.assertEqual(verif_prix.prix_officiel(h, URL), 100)

    def test_ancien_booleen_ne_valide_pas(self):
        x = {'prix': 30, 'prix_page': 30, 'prix_verifie': True, 'lien': URL}
        with patch('urllib.request.urlopen', side_effect=OSError('hors réseau')):
            self.assertEqual(verif_prix.controler(x)['statut'], 'inconnu')

    def test_recu_pc_frais_et_ecart_un_centime(self):
        x = {'prix': 100, 'lien': URL, 'preuve_prix': {'verifie_le': NOW, 'lien': URL,
             'devise': 'EUR', 'disponibilite': 'InStock', 'identite_confirmee': True, 'prix_page': 102}}
        with patch('urllib.request.urlopen', side_effect=AssertionError('pas de réseau')):
            self.assertEqual(verif_prix.controler(x)['statut'], 'different')
            x['preuve_prix']['prix_page'] = 100.01
            self.assertEqual(verif_prix.controler(x)['statut'], 'ok')

    def test_recu_perime_ne_contourne_pas_la_relecture(self):
        x = {'prix': 100, 'lien': URL, 'preuve_prix': {'verifie_le': '2000-01-01T00:00:00+00:00',
             'lien': URL, 'devise': 'EUR', 'disponibilite': 'InStock',
             'identite_confirmee': True, 'prix_page': 100}}
        with patch('urllib.request.urlopen', side_effect=OSError('hors réseau')):
            self.assertEqual(verif_prix.controler(x)['statut'], 'inconnu')

    def test_collecteur_pc_produit_un_recu_strict(self):
        from pc.collecteur import verifier_fiches
        class Page:
            url = URL
            def goto(self, *args, **kw):
                pass
            def wait_for_timeout(self, *args):
                pass
            def content(self):
                return html(produit())
        x = {'lien': URL, 'prix': 99, 'description': '-50 %'}
        with patch('pc.collecteur.time.sleep'):
            verifier_fiches(Page(), [x])
        self.assertEqual(x['prix'], 100)
        self.assertTrue(x['preuve_prix']['identite_confirmee'])
        with patch('urllib.request.urlopen', side_effect=AssertionError('pas de réseau')):
            self.assertEqual(verif_prix.controler(x)['statut'], 'ok')

    def test_page_bon_plan_non_marchande(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('pas de réseau')):
            self.assertEqual(verif_prix.controler({'lien': 'https://www.dealabs.com/test', 'prix': 10})['statut'], 'inconnu')


class ProduitTests(unittest.TestCase):
    def test_couleur_differente(self):
        self.assertIs(meme_produit.mecanique('Modèle noir', 'Modèle blanc')[0], False)
        self.assertIsNone(meme_produit.mecanique('Modèle noir', 'Modèle black')[0])

    def test_lots_differents(self):
        self.assertIs(meme_produit.mecanique('roue lot de 1', 'roue lot de 2')[0], False)

    def test_unites_equivalentes(self):
        self.assertIsNone(meme_produit.mecanique('Disque 1 To', 'Disque 1000 Go')[0])
        self.assertIsNone(meme_produit.mecanique('Moteur 1 kW', 'Moteur 1000 W')[0])
        self.assertIs(meme_produit.mecanique('Disque 1 To', 'Disque 2000 Go')[0], False)


class ValidationTests(unittest.TestCase):
    def test_vert_avec_preuves_et_marge(self):
        self.assertEqual(validation.blocages(candidat()), [])
        self.assertEqual(fiche.evaluer(candidat(), {})['feu'], 'vert')

    def test_preuves_manquantes_restent_orange(self):
        for key in ['controle_prix', 'meme_produit', 'livraison_fr_confirmee', 'cout_total_confirme']:
            x = candidat()
            del x[key]
            with self.subTest(key=key):
                self.assertEqual(fiche.evaluer(x, {})['feu'], 'orange')

    def test_ancien_prix_refuse(self):
        x = candidat()
        x['controle_prix']['verifie_le'] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.assertTrue(validation.blocages(x))

    def test_date_naive_future_et_variante_refusees(self):
        self.assertFalse(validation.recent('2026-11-05T12:00:00'))
        self.assertFalse(validation.recent((datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()))
        x = candidat()
        x['controle_prix']['lien'] = URL.replace('noir', 'blanc')
        self.assertTrue(validation.blocages(x))

    def test_plus_de_probabilite_non_calibree(self):
        f = fiche.evaluer({**candidat(), 'ventes_estimees_30j': 100}, {})
        self.assertIsNone(f['proba_vente_7j'])
        self.assertIn('indicateurs_demande', f)

    def test_telegram_hors_reseau(self):
        with patch.object(telegram, 'envoyer', return_value=True) as envoi:
            self.assertTrue(telegram.alerte(candidat(), {}))
        texte = envoi.call_args.args[0]
        self.assertIn('avant frais mensuels', texte)
        self.assertNotIn('Probabilité', texte)

    def test_publication_deduplique_et_ecarte_sans_preuve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            x, y = candidat(), candidat()
            y['id'] = 'doublon'
            z = candidat()
            z['id'], z['lien'] = 'non_verifie', 'https://marchand.example/z'
            (root / 'data/alertes.json').write_text(json.dumps([x, y, z]))
            with patch.object(construire_site, 'RACINE', str(root)):
                self.assertEqual(len(construire_site.affaires()), 1)


if __name__ == '__main__':
    unittest.main()
