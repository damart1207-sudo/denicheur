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


class Payant(unittest.TestCase):
    def test_recherches_payantes_seulement_si_le_produit_se_vend(self):
        appels = []
        def source(nom):
            return lambda *a: appels.append(nom) or {"nb": 0, "prix_min": None, "neuf": {"nb": 0}, "occasion": {"nb": 0}}
        peu, bien = fiche(asin="PEU", ventes_estimees_30j=2), fiche(asin="BIEN", ventes_estimees_30j=35)
        with patch.object(marche, "leboncoin", source("leboncoin")), patch.object(marche, "vinted", source("vinted")), \
                patch.object(marche, "idealo", source("idealo")), patch.object(marche, "ebay_fr", source("ebay")), \
                patch.object(marche, "achatmoinscher", source("achatmoinscher")):
            marche.etudier([peu, bien])
        self.assertEqual(sorted(appels), ["achatmoinscher", "achatmoinscher", "ebay", "ebay", "idealo", "leboncoin", "vinted"])
        self.assertTrue(peu["marche"]["gratuit_seul"])
        self.assertIn("pas vérifiés, le produit se vend trop peu", ecart.message(peu))
        self.assertIn("Leboncoin : aucune annonce", ecart.message(bien))
        self.assertTrue(marche.se_vend(fiche(achetes_mois_amazon=50)))


class Retenue(unittest.TestCase):
    def test_seules_les_affaires_qui_se_vendent_sont_retenues(self):
        regles = ecart._lire(os.path.join(ecart.RACINE, "config/regles.json"), {})
        offre = lambda prix: {"condition": 1, "offerCSV": [0, prix, 0]}
        a = {"asin": "B0X", "titre": "Sennheiser RS 195-U Casque sans Fil", "lien": "l", "moyenne_90j": 300.0, "rang": 3186}
        def produit(ventes):
            return {"title": a["titre"], "brand": "Sennheiser", "offers": [offre(21999), offre(31000)], "eanList": ["4044155092011"],
                    "stats": {"current": [0, 0, 0, 3186], "salesRankDrops30": ventes}}
        peu, bien = ecart.analyser(produit(2), a, regles), ecart.analyser(produit(35), a, regles)
        self.assertFalse(peu["retenu"])
        self.assertIn("se vend trop peu", peu["raison"])
        self.assertTrue(bien["retenu"])
        self.assertEqual((bien["ean"], bien["nom_court"]), ("4044155092011", "sennheiser rs 195-u casque"))
        self.assertGreaterEqual(apify.PLAFOND_JOUR_USD["E"], 1.0)


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

    def test_sens_inverse(self):
        f = fiche(premier=349.99, second=549.0, marche={"leboncoin": {"nb": 0}, "comparateurs_consultes": [],
                  "vinted": {"nb": 3, "min": 170.0, "max": 250.0, "lien_min": "u", "neuf": {"nb": 1, "min": 250.0, "max": 250.0, "lien_min": "v"}},
                  "ebay": {"nb": 1, "neuf": {"nb": 0}, "occasion": {"nb": 1, "min": 229.5, "max": 229.5, "lien_min": "e"}}})
        inv = marche.inverse(f)
        self.assertEqual((inv["site"], inv["prix"], inv["cout"], inv["ecart"]), ("vinted", 250.0, 263.2, 86.79))   # l'occasion à 170 € ne compte pas
        self.assertIn("Sens inverse</b>", ecart.message(f))
        self.assertIn("Sens inverse : une annonce NEUVE à 250 € sur vinted", self.b.fiche_texte(f))
        ac = {"acheter": "OUI", "raisons": "40 € de moins qu'Amazon."}
        b = self.b.valider(f, {"expert": {"vendre": "OUI", "achat": "vinted", "ou": "leboncoin", "prix": 310, "raisons": "x"}, "acheteur": ac}, self.regles)
        self.assertEqual((b["achat"], b["cout_achat"], b["prix"], b["marge_sans_charges"]), ("vinted", 263.2, 310.0, 46.8))
        f["bilan"] = b
        self.assertIn("En l'achetant sur <b>Vinted</b> à 250 €", ecart.message(f))
        for expert in ({"vendre": "OUI", "achat": "vinted", "ou": "amazon", "prix": 320, "raisons": "x"},      # jamais revendu sur Amazon
                       {"vendre": "OUI", "achat": "vinted", "ou": "leboncoin", "prix": 360, "raisons": "x"},   # au-dessus du moins cher d'Amazon
                       {"vendre": "OUI", "achat": "ebay", "ou": "leboncoin", "prix": 300, "raisons": "x"}):    # pas d'annonce neuve relevée sur eBay
            self.assertIsNone(self.b.valider(f, {"expert": expert, "acheteur": ac}, self.regles))
        f["marche"]["vinted"]["neuf"]["min"] = 320.0   # moins de 50 € d'écart : pas de sens inverse
        self.assertIsNone(marche.inverse(f))

    def test_grille_du_programme(self):
        self.f["ventes_estimees_30j"] = 40
        g = self.b.grille(self.f, self.regles)
        self.assertEqual((g["demande"], g["ref_nom"], g["plafond"], g["marge_sans"], g["vetos"], g["vendable"]),
                         ("forte", "le comparateur idealo", 132.05, 39.86, [], True))
        # prix au-dessus du maximum de la grille : avis rejeté, même sous le 2e vendeur
        ac = {"acheter": "NON", "raisons": "x"}
        self.assertIsNone(self.b.valider(self.f, {"expert": {"vendre": "OUI", "ou": "leboncoin", "prix": 138, "raisons": "x"}, "acheteur": ac}, self.regles))
        # eBay : 13 % de frais, la marge passe sous 20 € -> rejeté
        self.assertIsNone(self.b.valider(self.f, {"expert": {"vendre": "OUI", "ou": "ebay", "prix": 130, "raisons": "x"}, "acheteur": ac}, self.regles))
        # déjà au prix d'achat dans le comparateur : refus automatique, un OUI de l'IA est rejeté
        self.f["marche"]["comparateur_min"] = {"prix": 93.0, "ou": "idealo", "nb_offres": 30, "lien": None, "ecart": 0.81}
        g = self.b.grille(self.f, self.regles)
        self.assertFalse(g["vendable"])
        self.assertEqual(len(g["vetos"]), 2)
        self.assertIn("REFUSE la vente", self.b.grille_texte(g))
        self.assertIsNone(self.b.valider(self.f, {"expert": {"vendre": "OUI", "ou": "leboncoin", "prix": 110, "raisons": "x"}, "acheteur": ac}, self.regles))
        b = self.b.sans_ia(self.f, g)
        self.assertIn("déjà affiché à 93 € sur idealo", b["raisons_expert"])
        self.assertIn("Ce qui ferait tout rater", "\n".join(self.b.lignes({"bilan": {**self.b.valider(fiche(ventes_estimees_30j=40, marche={}), {"expert": {
            "vendre": "OUI", "ou": "leboncoin", "prix": 129.9, "raisons": "x", "condition": "Si l'offre à 92 € reste en ligne."}, "acheteur": ac}, self.regles)}})))
        self.assertIn("LE PRODUIT SE VEND", self.b.formation())

    def test_sans_ia_pas_de_bilan(self):
        vide = {k: "" for k in ("GEMINI_API_KEY", "NVIDIA_API_KEY", "ZAI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")}
        with patch.dict(os.environ, vide):
            b = self.b.rediger(self.f)                       # demande faible : le programme refuse lui-même, chiffres à l'appui
            self.assertEqual((b["vendre"], b["ia"]), (False, "programme"))
            self.assertIn("se vend trop peu", b["raisons_expert"])
            self.f["ventes_estimees_30j"] = 40               # tout est bon : le programme ne dit jamais OUI tout seul
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
