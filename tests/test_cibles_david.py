"""Les cibles données par David (config/cibles_david.json) entrent dans la liste de chasse d'Amigo."""
import json
import os
import unittest

from denicheur import demande

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CiblesDavid(unittest.TestCase):
    def setUp(self):
        self.cibles = json.load(open(os.path.join(RACINE, "config/cibles_david.json"), encoding="utf-8"))
        self.liste = demande.liste_de_chasse({"liste": []})

    def test_format(self):
        for c in self.cibles:
            self.assertTrue(c.get("nom"))
            self.assertIsInstance(c.get("variantes", []), list)

    def test_en_tete_de_liste(self):
        if not self.cibles:
            self.skipTest("aucune cible")
        self.assertEqual(self.liste[0]["origine"], "david")
        noms = {x["recherche"] for x in self.liste if x.get("origine") == "david"}
        for c in self.cibles:
            self.assertIn(c["nom"], noms)

    def test_titres_reconnus(self):
        noms = {c["nom"] for c in self.cibles}
        cas = {"kpop demon hunters": ["Poupée Mattel KPop Demon Hunters Rumi", "Monopoly K-Pop Demon Hunters Hasbro"],
               "flip 7 vengeance": ["Flip 7 Vengeance - jeu de cartes"],
               "squishy": ["Squishy géant", "Lot de 12 squishies kawaii"],
               "pokemon": ["Coffret Pokémon 30e anniversaire", "Cartes Pokemon"]}
        for nom, titres in cas.items():
            if nom not in noms:
                continue
            for t in titres:
                dm = demande.est_demande(t, {"liste": []})
                self.assertIsNotNone(dm, t)
                self.assertEqual(dm.get("cible"), nom, t)

    def test_pas_de_faux_ami(self):
        if "flip 7 vengeance" in {c["nom"] for c in self.cibles}:
            dm = demande.est_demande("Flip 7 jeu de cartes", {"liste": []})
            self.assertTrue(dm is None or dm.get("cible") != "flip 7 vengeance")


if __name__ == "__main__":
    unittest.main()
