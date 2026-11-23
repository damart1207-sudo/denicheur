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

    # ---- résultats RÉELS de la recherche Keepa sur Amazon.fr, relevés le 23/11/2026 (titre, prix, classement) ----
    def choix(self, labas, prix, resultats):
        prods = [produit(f"B0FR{i:06d}", t, p or 0, rg, marque=m) for i, (t, p, rg, m) in enumerate(resultats)]
        return moisson.choisir_par_nom(labas, prods, prix)

    def test_jessie_et_pas_l_alien(self):
        x = self.choix(JESSIE_US, 28.8, [
            ("Disney Store Official, Figurine Jessie parlante, Toy Story, 36 cm", 41.99, 2365, "Disney Store"),
            ("Disney Store Official, Figurine Rex parlante, Toy Story, 34 cm", 35.69, 2538, "Disney Store"),
            ("Disney Store Official Figurine Alien parlante interactive, Toy Story", 33.99, 112, "Disney Store"),
            ("Disney Store Official Peluche Pile-Poil de taille moyenne, Toy Story", 32.0, 2910, "Disney Store"),
            ("Mattel Toy Story 5 Figurine Buzz Lightyear Mode Vol", 31.41, 794, "Mattel")])
        self.assertEqual(x["neuf"], 41.99)

    def test_dualsense_et_pas_la_edge(self):
        us = moisson.resumer(produit("B0FY6Y9WZT", "PlayStation DualSense™ Wireless Controller – Midnight Black", 54, 1, marque="PlayStation"), "US")
        x = self.choix(us, 48.6, [
            ("Playstation DualSense Edge® Wireless-Controller – Midnight Black", 179.99, 109, "PlayStation"),
            ("Playstation®5-1 TB 2x DualSense® Wireless Controller Bundle", 1329.0, 13, "PlayStation"),
            ("Playstation Sony, Manette 5 Officielle DualSense, Sans Fil, Midnight Black", 55.99, 2, "PlayStation"),
            ("Playstation Sony, Manette 5 DualSense Edge, Sans Fil, Touches Arrière", 179.99, 140, "PlayStation")])
        self.assertEqual(x["neuf"], 55.99)

    def test_un_accessoire_n_est_pas_le_produit(self):
        us = moisson.resumer(produit("B09B2QTGFY", "Amazon Echo Show 5 (newest model), Smart display", 55, 2, marque="Amazon"), "US")
        self.assertIsNone(self.choix(us, 49.49, [
            ("Amazon | Adaptateur secteur de rechange officiel pour Echo Dot et Echo Show 5", 19.99, 49, "Amazon"),
            ("Adaptateur secteur de rechange pour Amazon Echo Show 5 (3e génération)", 20.39, 186, "Amazon"),
            ("Support réglable avec port de charge USB-C pour Echo Show 5 (3e génération)", 26.59, 103, "Amazon"),
            ("Savvies Film Protection pour Amazon Echo Show 5", 5.42, None, "Savvies")]))

    def test_roku_non_vendu_en_france_reste_introuvable(self):
        us = moisson.resumer(produit("B0DXXYS4BJ", "Roku Streaming Stick HD with Voice Remote", 19, 5, marque="Roku"), "US")
        self.assertIsNone(self.choix(us, 17.1, [
            ("Roku® Streaming Stick™ Plus 2025 – Appareil de Streaming Roku 4K et HD", 55.93, 13866, "Roku"),
            ("Roku Bâton de Diffusion en continu", 45.56, 25178, "Roku"),
            ("Roku Streaming Stick+ (HD, 4K, HDR) Streaming Device USER GUIDE", 14.34, 702184, None),
            ("ROKU STREAMING STICK HD USER GUIDE MADE EASY", 15.31, None, None)]))

    def test_annonces_d_import_des_draps_refusees(self):
        us = moisson.resumer(produit("B06WWRCZXX", "Queen Size 4 Piece Sheet Set - Breathable & Cooling Sheets", 20, 2, marque="CGK Unlimited"), "US")
        self.assertIsNone(self.choix(us, 18.14, [
            ("Queen Size 4 Piece Sheet Set - Comfy Breathable & Cooling Sheets - Hotel", 46.66, 65079, "CGK Unlimited"),
            ("Utopia Bedding Ensemble de Drap 4 Pièces, 180x200cm, Bleu Denim", 23.74, 1405, "Utopia Bedding")]))

if __name__ == "__main__":
    unittest.main()
