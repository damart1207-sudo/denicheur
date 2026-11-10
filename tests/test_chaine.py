import json
import unittest

from denicheur import chaine

REGLES = {"plateformes_revente": {"rebifftout": {"commission": 0.015, "frais_fixes": 0.25, "port": 0.0}}}


def page(*produits):
    return "".join(f'<script type="application/ld+json">{json.dumps(p)}</script>' for p in produits)


def produit(gtin="3165140761420", prix="129.90", dispo="https://schema.org/InStock", **k):
    return {"@type": "Product", "name": "Perceuse Bosch GSR 18V-55", "gtin13": gtin,
            "offers": {"@type": "Offer", "price": prix, "priceCurrency": "EUR", "availability": dispo}, **k}


class CodesTests(unittest.TestCase):
    def test_cle_de_controle(self):
        self.assertTrue(chaine.ean_valide("3165140761420"))
        self.assertFalse(chaine.ean_valide("3165140761421"))   # un chiffre faux
        self.assertFalse(chaine.ean_valide("0000000000000"))
        self.assertFalse(chaine.ean_valide("12345"))
        self.assertEqual(chaine.ean13("03165140761420"), "3165140761420")
        self.assertIsNone(chaine.ean13("B0CTTC2M6N"))

    def test_asin_amazon(self):
        self.assertEqual(chaine.asin_de("https://www.amazon.fr/dp/B08X21QX27/?tag=x"), ("B08X21QX27", "FR"))
        self.assertEqual(chaine.asin_de("https://www.amazon.fr/s?k=perceuse"), (None, "FR"))
        self.assertEqual(chaine.asin_de("https://www.fnac.com/a123"), (None, None))


class FicheTests(unittest.TestCase):
    def test_fiche_simple(self):
        f = chaine.lire_fiche(page(produit()))
        self.assertEqual((f["ean"], f["prix"], f["etat"]), ("3165140761420", 129.9, "neuf"))

    def test_page_a_variantes_refusee(self):
        f = chaine.lire_fiche(page(produit(), produit(gtin="4006381333931", prix="99")))
        self.assertNotIn("ean", f)
        self.assertIn("variantes", f["raison"])

    def test_sans_code_refusee(self):
        p = produit()
        del p["gtin13"]
        self.assertIn("pas de code", chaine.lire_fiche(page(p))["raison"])

    def test_rupture_ou_occasion(self):
        self.assertIsNone(chaine.lire_fiche(page(produit(dispo="https://schema.org/OutOfStock")))["prix"])
        p = produit()
        p["offers"]["itemCondition"] = "https://schema.org/UsedCondition"
        self.assertEqual(chaine.lire_fiche(page(p))["etat"], "pas neuf")

    def test_code_attendu(self):
        self.assertIn("attendu", chaine.lire_fiche(page(produit()), "4006381333931")["raison"])


class VerdictTests(unittest.TestCase):
    def refs(self, *prix, gros=True):
        return [{"marchand": f"M{i}", "total": p, "gros": gros} for i, p in enumerate(prix)]

    def test_vert(self):
        v = chaine.verdict(100, self.refs(150, 155, 160), True, REGLES)
        self.assertEqual(v["feu"], "vert")
        self.assertEqual(v["prix_vente"], 145.5)
        self.assertGreaterEqual(v["marge_nette"], 20)

    def test_pas_moins_cher(self):
        self.assertEqual(chaine.verdict(100, self.refs(104, 110, 120, 125, 130), True, REGLES)["feu"], "rouge")

    def test_concurrence_dix_vendeurs_gros_au_meme_prix(self):
        v = chaine.verdict(100, self.refs(*([130] * 9)) + self.refs(101), True, REGLES)
        self.assertEqual(v["feu"], "rouge")

    def test_orange_si_prix_non_confirme_ou_reference_unique(self):
        self.assertEqual(chaine.verdict(100, self.refs(150, 155), False, REGLES)["feu"], "orange")
        self.assertEqual(chaine.verdict(100, self.refs(150), True, REGLES)["feu"], "orange")
        self.assertEqual(chaine.verdict(100, self.refs(150, 220), True, REGLES)["feu"], "orange")

    def test_ecart_anormal_jamais_vert(self):
        self.assertEqual(chaine.verdict(30, self.refs(150, 155), True, REGLES)["feu"], "orange")

    def test_petite_marge_rouge(self):
        self.assertEqual(chaine.verdict(20, self.refs(25, 26), True, REGLES)["feu"], "rouge")


class ConcordanceTests(unittest.TestCase):
    def test_google_repond_un_autre_produit(self):
        self.assertFalse(chaine.concorde("Tineco A30S Aspirateur Balai sans Fil, 160W", "Casque gamer HyperX Cloud Alpha 2 sans fil", "Tineco"))

    def test_meme_modele(self):
        self.assertTrue(chaine.concorde("dreame L10s Pro Gen 3 Robot Aspirateur Laveur, 13 000 Pa", "Dreame L10s Pro Gen 3 Noir Robot Aspirateur Laveur", "dreame"))
        self.assertTrue(chaine.concorde("Moulinex - Multisoup Blender Chauffant 850W Capacité 1.2 L", "Moulinex Multisoup Blender", "Moulinex"))

    def test_autre_modele_de_la_meme_marque(self):
        self.assertFalse(chaine.concorde("Tineco A30S Aspirateur Balai", "Tineco Floor One S5 aspirateur laveur", "Tineco"))

    def test_amazon_com_depuis_une_source_francaise(self):
        self.assertEqual(chaine.asin_de("https://www.amazon.com/dp/B08X21QX27"), ("B08X21QX27", "FR"))


if __name__ == "__main__":
    unittest.main()
