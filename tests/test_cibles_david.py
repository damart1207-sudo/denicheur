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
               "pokemon": ["Coffret Pokémon 30e anniversaire", "Cartes Pokemon"],
               "galaxy a16": ["Samsung Galaxy A16 4G 128 Go Noir", "Smartphone SAMSUNG Galaxy A16 128Go Bleu nuit 4G"]}
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

    def test_prix_max_bloque_au_dessus(self):
        """Galaxy A16 : alerte seulement à 75 € ou moins (au-dessus, aucune marge à la revente)."""
        if "galaxy a16" not in {c["nom"] for c in self.cibles}:
            self.skipTest("cible retirée")
        t = "Samsung Galaxy A16 4G 128 Go Noir"
        self.assertTrue(demande.au_dessus_du_prix_max(t, 99.0, {"liste": []}))
        self.assertTrue(demande.au_dessus_du_prix_max(t, 75.01, {"liste": []}))
        self.assertFalse(demande.au_dessus_du_prix_max(t, 75.0, {"liste": []}))
        self.assertFalse(demande.au_dessus_du_prix_max(t, 59.9, {"liste": []}))
        # un autre téléphone ou une cible sans plafond ne sont jamais bloqués
        self.assertFalse(demande.au_dessus_du_prix_max("Samsung Galaxy A17 5G 128 Go", 150.0, {"liste": []}))
        self.assertFalse(demande.au_dessus_du_prix_max("Coffret Pokémon 30e anniversaire", 150.0, {"liste": []}))

    def test_chasseur_pc_prix_max(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("chasseur", os.path.join(RACINE, "pc", "chasseur.py"))
        ch = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(ch)
        except ImportError:
            self.skipTest("dépendances du PC absentes")
        c = {"nom": "galaxy a16", "prix_max": 75, "etat": "neuf"}
        self.assertTrue(ch.garde_prix_max(c, {"titre": "Samsung Galaxy A16 neuf sous blister", "prix": 70.0}))
        self.assertTrue(ch.garde_prix_max(c, {"titre": "Galaxy A16 128go jamais ouvert", "prix": 75.0}))
        self.assertFalse(ch.garde_prix_max(c, {"titre": "Samsung Galaxy A16 neuf scellé", "prix": 100.0}))   # trop cher
        self.assertFalse(ch.garde_prix_max(c, {"titre": "Coque Samsung Galaxy A16 neuve", "prix": 5.0}))    # accessoire
        self.assertFalse(ch.garde_prix_max(c, {"titre": "Samsung Galaxy A16 écran fissuré", "prix": 60.0}))  # pas neuf
        self.assertFalse(ch.garde_prix_max(c, {"titre": "Samsung Galaxy S24 neuf", "prix": 70.0}))           # autre modèle
        david = [x for x in ch.cibles() if x["nom"] == "galaxy a16"]
        self.assertEqual(david[0]["prix_max"], 75)


if __name__ == "__main__":
    unittest.main()
