"""Marché des écarts vendeurs : nom court, fourchettes, texte de l'alerte, file d'attente tour -> suite. Hors réseau."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from denicheur import apify, ecart, marche


def fiche(**k):
    f = {"asin": "B0TEST", "titre": "iiyama G-Master GB2771HSU-W1 Écran 27 pouces, Blanc", "marque": "iiyama", "lien": "https://www.amazon.fr/dp/B0TEST",
         "moyenne_90j": 140.0, "nb_offres_neuves": 5, "premier": 92.19, "second": 142.59, "ecart": 50.4, "retenu": True,
         "mot_cle": "iiyama g-master gb2771hsu-w1 écran", "nom_court": "iiyama g-master gb2771hsu-w1 écran",
         "vu": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
         "marges": ecart.marges(92.19, 142.59, ecart._lire(os.path.join(ecart.RACINE, "config/regles.json"), {}))}
    f.update(k)
    return f


class NomCourt(unittest.TestCase):
    def test_sans_mots_vides(self):
        self.assertEqual(marche.nom_court("Seac Privilege Combinaison avec Veste à Cagoule", "SEAC"), "seac privilege combinaison veste")
        self.assertEqual(marche.nom_court("EDGE 50 NEO 8/256 POINCIANA", "Motorola"), "motorola edge 50 neo")

    def test_variantes(self):
        self.assertEqual(marche.variantes("motorola edge 50 neo"), ["motorola edge 50 neo", "motorola edge 50"])
        self.assertEqual(marche.variantes("dyson v12"), ["dyson v12"])


class Sources(unittest.TestCase):
    def test_vinted_filtre_titre_et_bornes(self):
        items = [{"title": "Motorola Edge 50 Neo", "price_amount": "250.00", "status": "Très bon état", "url": "u1"},
                 {"title": "Motorola Edge 50 Neo neuf", "price_amount": "330.00", "status": "Neuf avec étiquette", "url": "u2"},
                 {"title": "Coque Motorola Edge 50 Neo", "price_amount": "8.00", "status": "Neuf", "url": "u3"},
                 {"title": "Motorola Edge 50 Ultra", "price_amount": "400.00", "status": "Bon état", "url": "u4"}]
        with patch.object(apify, "_lancer", return_value=items):
            r = marche.vinted("motorola edge 50 neo", 105, 1098)
        self.assertEqual((r["nb"], r["min"], r["max"], r["lien_min"]), (2, 250.0, 330.0, "u1"))
        self.assertEqual((r["neuf"]["nb"], r["neuf"]["min"]), (1, 330.0))

    def test_source_muette_differe_de_aucune_annonce(self):
        with patch.object(apify, "_lancer", return_value=None):
            self.assertIsNone(marche.leboncoin("motorola edge 50 neo", 1, 999))
        with patch.object(apify, "_lancer", return_value=[]):
            self.assertEqual(marche.leboncoin("motorola edge 50 neo", 1, 999), {"nb": 0})

    def test_leboncoin_prix(self):
        items = [{"title": "Motorola Edge 50 néo", "price": 199, "url": "l1"}, {"title": "Motorola edge 50 neo 512", "price": 270, "url": "l2"},
                 {"title": "Motorola Edge 30 Ultra 256Go", "price": 500, "url": "l3"}, {"title": "Coque motorola edge 50 neo", "price": 5, "url": "l4"}]
        with patch.object(apify, "_lancer", return_value=items):
            self.assertEqual(marche.leboncoin("motorola edge 50 neo", 100, 999), {"nb": 2, "min": 199.0, "max": 270.0, "lien_min": "l1"})


class Dates(unittest.TestCase):
    def test_anciennete_des_annonces(self):
        from datetime import timedelta
        j = lambda n: (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT10:00:00Z")
        r = marche._fourchette([(80.0, "a", j(26)), (120.0, "b", j(2)), (150.0, "c", j(40)), (130.0, "d", None)])
        self.assertEqual((r["nb"], r["dates"], r["age_min"], r["age_recent"], r["age_ancien"], r["recentes"], r["anciennes"]), (4, 3, 26, 2, 40, 1, 2))
        self.assertIsNone(marche.age_jours("hier"))
        self.assertEqual(marche.age_jours((datetime.now(timezone.utc) - timedelta(days=3)).timestamp()), 3)
        f = fiche(marche={"leboncoin": r, "vinted": {"nb": 0, "neuf": {"nb": 0}}, "ebay": None, "comparateurs_consultes": []})
        t = ecart.message(f)
        self.assertIn("en ligne depuis 26 j)", t)
        self.assertIn("1 publiée cette semaine · 2 en ligne depuis plus de 21 j · la plus ancienne : 40 j", t)
        self.assertIn("⏳ Leboncoin : l'annonce à 80 € est en ligne depuis 26 j sans se vendre", t)


class Texte(unittest.TestCase):
    def test_alerte_complete(self):
        f = fiche(volume=1900, volume_mot="iiyama g-master gb2771hsu-w1", marche={
            "leboncoin": {"nb": 3, "min": 80.0, "max": 150.0, "lien_min": "https://lbc/1"},
            "vinted": {"nb": 0, "neuf": {"nb": 0}},
            "ebay": {"nb": 2, "neuf": {"nb": 2, "min": 135.0, "max": 160.0, "lien_min": "https://ebay/1"}, "occasion": {"nb": 0}},
            "comparateurs_consultes": ["idealo", "achatmoinscher"],
            "comparateur_min": {"prix": 139.0, "ou": "idealo", "nb_offres": 12, "lien": "https://idealo/1", "ecart": 46.81}})
        t = ecart.message(f)
        self.assertIn("1 900</b>/mois", t)
        self.assertIn("le moins cher à <b>139 €</b>", t)
        self.assertIn("46,81 € en dessous", t)
        self.assertIn("Leboncoin : 3 annonces, de 80 € à 150 €", t)
        self.assertIn("Vinted : aucune annonce", t)
        self.assertIn("eBay neuf : 2 annonces, de 135 € à 160 €", t)
        self.assertIn("eBay occasion : aucune annonce", t)
        self.assertIn("Déjà à 80 € sur Leboncoin", t)   # sous le prix de revente conseillé (117 €)
        self.assertLess(len(t), 4000)

    def test_source_non_consultee_et_comparateur_au_meme_prix(self):
        f = fiche(marche={"leboncoin": None, "vinted": None, "ebay": None, "comparateurs_consultes": ["achatmoinscher"],
                          "comparateur_min": {"prix": 93.0, "ou": "achatmoinscher", "nb_offres": None, "lien": None, "ecart": 0.81}})
        t = ecart.message(f)
        self.assertIn("Leboncoin : non consulté", t)
        self.assertIn("déjà affiché à ce prix dans les comparateurs", t)
        self.assertNotIn("aucune annonce", t)

    def test_introuvable_dans_les_comparateurs(self):
        f = fiche(marche={"leboncoin": {"nb": 0}, "vinted": {"nb": 0, "neuf": {"nb": 0}}, "ebay": {"nb": 0, "neuf": {"nb": 0}, "occasion": {"nb": 0}},
                          "comparateurs_consultes": ["idealo", "achatmoinscher"]})
        self.assertIn("introuvable sur idealo et achatmoinscher", ecart.message(f))


class Bilan(unittest.TestCase):
    def setUp(self):
        from denicheur import bilan
        self.b = bilan
        self.regles = ecart._lire(os.path.join(ecart.RACINE, "config/regles.json"), {})
        self.f = fiche(volume=1900, volume_mot="iiyama gb2771hsu", marche={
            "leboncoin": {"nb": 2, "min": 80.0, "max": 150.0, "lien_min": "l", "dates": 2, "age_min": 26, "age_recent": 3, "age_ancien": 26, "recentes": 1, "anciennes": 1},
            "vinted": None, "ebay": {"nb": 0, "neuf": {"nb": 0}, "occasion": {"nb": 0}}, "comparateurs_consultes": ["idealo"],
            "comparateur_min": {"prix": 139.0, "ou": "idealo", "nb_offres": 12, "lien": None, "ecart": 46.81}})

    def test_fiche_ne_contient_que_les_chiffres_releves(self):
        t = self.b.fiche_texte(self.f)
        for attendu in ("92,19 €", "142,59 €", "1900 pour « iiyama gb2771hsu »", "139 € sur idealo (12 offres)",
                        "la moins chère est en ligne depuis 26 jours", "Vinted : non consulté (inconnu)", "eBay neuf : aucune annonce"):
            self.assertIn(attendu, t)

    def test_avis_valide_et_marges_recalculees(self):
        b = self.b.valider(self.f, {"expert": {"vendre": "oui", "ou": "Leboncoin", "prix": "119,00 €", "raisons": "Tu es 47 € sous idealo.", "marge": 999},
                                    "acheteur": {"acheter": "OUI", "raisons": "20 € de moins qu'idealo."}}, self.regles)
        self.assertEqual((b["vendre"], b["ou"], b["prix"], b["marge_sans_charges"], b["acheter"]), (True, "leboncoin", 119.0, 26.81, True))
        self.assertAlmostEqual(b["marge_avec_charges"], round(119 - 92.19 - 119 * 0.134 - 3, 2), places=2)
        self.f["bilan"] = b
        t = ecart.message(self.f)
        self.assertIn("Je le vends</b> : sur <b>Leboncoin</b> à <b>119 €</b>", t)
        self.assertIn("Oui, j'achète</b> : 20 € de moins qu'idealo.", t)

    def test_avis_rejetes(self):
        ok = {"acheter": "NON", "raisons": "Trop cher."}
        for expert in ({"vendre": "OUI", "ou": "leboncoin", "prix": 150, "raisons": "x"},      # au-dessus du 2e vendeur
                       {"vendre": "OUI", "ou": "leboncoin", "prix": 90, "raisons": "x"},       # sous le prix d'achat
                       {"vendre": "OUI", "ou": "cdiscount", "prix": 120, "raisons": "x"},      # site hors liste
                       {"vendre": "PEUT-ÊTRE", "raisons": "x"}, {"vendre": "NON", "raisons": ""}):
            self.assertIsNone(self.b.valider(self.f, {"expert": expert, "acheteur": ok}, self.regles))
        self.assertIsNone(self.b.valider(self.f, None, self.regles))
        b = self.b.valider(self.f, {"expert": {"vendre": "NON", "ou": None, "prix": None, "raisons": "Annonce à 80 € depuis 26 jours."}, "acheteur": ok}, self.regles)
        self.assertEqual((b["vendre"], b["acheter"], "prix" in b), (False, False, False))
        self.f["bilan"] = b
        self.assertIn("Je ne le vends pas", ecart.message(self.f))

    def test_sans_ia_pas_de_bilan(self):
        with patch.dict(os.environ, {k: "" for k in ("GEMINI_API_KEY", "NVIDIA_API_KEY", "ZAI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")}):
            self.assertIsNone(self.b.rediger(self.f))
        self.f["bilan"] = None
        self.assertNotIn("BILAN", ecart.message(self.f))


class Suite(unittest.TestCase):
    def test_suite_etudie_enregistre_envoie_une_fois(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "ecarts.json")
            jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            vieux = fiche(asin="B0VIEUX", a_envoyer=True, vu=jour + "T00:00") if datetime.now(timezone.utc).hour >= 2 else None
            affaires = [fiche(a_envoyer=True)] + ([vieux] if vieux else [])
            json.dump({"jour": jour, "affaires": affaires}, open(chemin, "w"))
            envois = []

            def etude(lot):
                for f in lot:
                    f["marche"] = {"leboncoin": {"nb": 0}, "vinted": None, "ebay": None, "comparateurs_consultes": []}
            with patch.object(ecart, "F_ECARTS", chemin), patch.object(marche, "etudier", side_effect=etude) as et, \
                    patch.object(marche, "volumes", return_value={"iiyama g-master gb2771hsu-w1 écran": {"v": 320, "mot": "iiyama g-master gb2771hsu-w1"}}), \
                    patch("denicheur.bilan.rediger", return_value=None), \
                    patch("denicheur.telegram.envoyer", side_effect=lambda t: envois.append(t) or True):
                self.assertEqual(ecart.suite(), 1)
                self.assertEqual(ecart.suite(), 0)   # rien à renvoyer
            self.assertEqual(et.call_count, 1)
            self.assertEqual(len(envois), 1)
            self.assertIn("320</b>/mois", envois[0])
            base = json.load(open(chemin))
            self.assertTrue(all(not f.get("a_envoyer") for f in base["affaires"]))
            self.assertTrue(base["affaires"][0]["alerte"])
            if vieux:
                self.assertNotIn("alerte", base["affaires"][1])   # périmée : abandonnée sans envoi ni étude


if __name__ == "__main__":
    unittest.main()
