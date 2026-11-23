"""Régression du 23/11/2026 : le rapport « top 10 USA » annonçait Jessie (Toy Story) à 121 € « en France » (annonce d'un
importateur sur la fiche américaine) alors que la fiche française est à 40 €, et l'Echo Show 11 « absent d'Amazon France »."""
import unittest
from unittest import mock

from denicheur import classements, moisson


def produit(asin, titre, prix, rang, eans=(), marque=None, offres=3):
    cur = [-1] * 12
    cur[moisson.I_NEUF], cur[moisson.I_RANG], cur[moisson.I_NB_NEUF] = int(prix * 100), rang or -1, offres
    return {"asin": asin, "title": titre, "brand": marque, "eanList": list(eans), "stats": {"current": cur}}


JESSIE_US = moisson.resumer(produit("B07PN7FP76", "Disney Store Official Jessie Interactive Talking Action Figure from Toy Story, F",
                                    32, 3, ["0111111111111"], "Disney Store"), "US")
ECHO_US = moisson.resumer(produit("B0DC91H3JK", "Amazon Echo Show 11 (newest model), Vibrant Full-HD 11\" display", 155, 4, ["0222222222222"], "Amazon"), "US")
INCONNU_US = moisson.resumer(produit("B0INCONNU1", "Nex Playground - The Active Play System", 209, 2, ["0333333333333"], "Nex"), "US")


def faux_keepa(chemin, params, corps=None, *, etat=None, cout_max=None):
    if chemin == "product" and "asin" in params:      # même ASIN sur Amazon.fr : seule l'annonce d'import de Jessie existe
        return {"products": [produit("B07PN7FP76", "Disney Store Official Jessie Interactive Talking Action Figure", 121.39, None, offres=1)]}
    if chemin == "product" and "code" in params:      # code-barres : la fiche française de l'Echo Show
        return {"products": [produit("B0FRECHO11", "Amazon Echo Show 11 (dernier modèle), écran Full HD 11\"", 154.99, 120, ["0222222222222"], "Amazon")]}
    if chemin == "search" and "Jessie" in params["term"]:
        return {"products": [
            produit("B0FRWOODY1", "Disney Store Official Figurine Interactive Woody, Toy Story", 39.99, 900, marque="Disney Store"),
            produit("B0FRJESSIE", "Disney Store Official Figurine Interactive Jessie, Toy Story des Studios Pixar, 36 cm", 39.99, 1500, marque="Disney Store"),
            produit("B0FRCHAPO1", "Disney Store Chapeau Jessie Toy Story", 9.99, 800, marque="Disney Store")]}
    return {"products": []}


class FicheFrance(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(moisson, "_appel", side_effect=faux_keepa)
        p.start()
        self.addCleanup(p.stop)
        self.vues = moisson.fiche_france([JESSIE_US, ECHO_US, INCONNU_US],
                                         {"B07PN7FP76": 28.8, "B0DC91H3JK": 139.49, "B0INCONNU1": 188.1}, par_nom=10)

    def test_annonce_import_jamais_prise_pour_le_prix_francais(self):
        v = self.vues["B07PN7FP76"]
        self.assertEqual((v["etat"], v["asin"], v["prix"]), ("probable", "B0FRJESSIE", 39.99))
        self.assertEqual(v["import"]["prix"], 121.39)

    def test_sans_recherche_par_nom_l_import_est_dit_import(self):
        v = moisson.fiche_france([JESSIE_US], {"B07PN7FP76": 28.8})["B07PN7FP76"]
        self.assertEqual(v["etat"], "import")
        self.assertIn("pas le prix français", classements.ligne_france(v, lambda p: f"{p} €", str))

    def test_autre_numero_de_fiche_trouve_par_le_code_barres(self):
        v = self.vues["B0DC91H3JK"]
        self.assertEqual((v["etat"], v["trouve_par"], v["asin"], v["prix"]), ("fiche", "code-barres", "B0FRECHO11", 154.99))

    def test_rien_trouve_n_est_pas_absent(self):
        v = self.vues["B0INCONNU1"]
        self.assertEqual(v["etat"], "introuvable")
        t = classements.ligne_france(v, lambda p: f"{p} €", str)
        self.assertNotIn("absent", t)
        self.assertIn("à vérifier", t)

    def test_un_autre_modele_n_est_pas_le_meme_produit(self):
        self.assertEqual(moisson.ressemblance("Amazon Echo Show 11 (newest model)", "Amazon Echo Show 8 (dernier modèle)", "Amazon"), 0.0)
        self.assertGreaterEqual(moisson.ressemblance("Amazon Echo Show 11 (newest model)", "Amazon Echo Show 11 (dernier modèle)", "Amazon"), 0.5)


if __name__ == "__main__":
    unittest.main()
