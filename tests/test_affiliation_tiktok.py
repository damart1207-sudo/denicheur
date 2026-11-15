"""Affiliation TikTok Shop : calculs et rapport, sans réseau ni appel payant."""
import importlib.util
import json
import os
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("affiliation_tiktok", os.path.join(RACINE, "outils/affiliation_tiktok.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

FILTRES = {"prix_moyen_min_usd": 3, "ventes_min": 200, "evolution_min_pct": -20, "gain_par_vente_min_usd": 1.0}


def ligne(titre, ventes, prix, com, evo=10, cat="Beauty & Personal Care", lien=None):
    return {"rank": 1, "title": titre, "unitsSold": ventes, "avgSellingPrice": prix, "commissionRatePercent": com,
            "revenue": ventes * prix, "videoRevenue": ventes * prix * 0.9, "revenueGrowthPercent": evo,
            "category": cat, "url": lien or "https://shop.tiktok.com/fr/pdp/" + str(abs(hash(titre)))}


class Calculs(unittest.TestCase):
    def test_marque_et_mot_cle(self):
        t = "[medicube Officiel] Sérum raffermissant NAD+ EGF | Sérum avec NAD+, EGF & extrait de collagène"
        self.assertEqual(A.marque(t), "medicube")
        self.assertEqual(A.mot_cle(t), "medicube Sérum raffermissant NAD+ EGF")
        self.assertEqual(A.mot_cle("LANDOT Brosse électrique lissante 2 en 1 pour cheveux, peigne lissant"), "LANDOT Brosse électrique lissante")
        self.assertEqual(A.mot_cle("Fructis Méthode Boucles - Hydratation et Définition - Garnier"), "Fructis Méthode Boucles")
        self.assertEqual(A.marque(""), "")

    def test_marque_fiable_et_recherche(self):
        cas = {"[medicube Officiel] Sérum raffermissant NAD+ EGF | Sérum": "medicube", "[NYX PM] Epic Inky Stix": "NYX",
               "LANDOT Brosse électrique lissante 2 en 1 pour cheveux": "LANDOT", "CP PAPILLON 50ML - 23 VARIANTES": "CP PAPILLON",
               "Fructis Méthode Boucles - Hydratation et Définition - Garnier": "Garnier",
               # relevé réel du 15/11/2026 : ces titres ramenaient d'autres produits -> aucun recoupement
               "Manteau bloom": "", "Coffret de Noël – 6 squishies à presser": "", "Christmas Party Card Game, 250+ Game Cards": "",
               "Rose Mystik - Lingettes Intimes": "", "Lip liner - Crayon à lèvres": "", "KIT de magicien": "", "": ""}
        for titre, attendu in cas.items():
            self.assertEqual(A.marque_fiable(titre), attendu, titre)
        self.assertEqual(A.recherche("LANDOT Brosse électrique lissante 2 en 1 pour cheveux, peigne", "LANDOT"), "LANDOT Brosse électrique lissante")
        self.assertEqual(A.recherche("[medicube Officiel] Sérum raffermissant NAD+ EGF | Sérum avec", "medicube"), "medicube Sérum raffermissant NAD+")
        self.assertEqual(A.recherche("Fructis Méthode Boucles - Hydratation - Garnier", "Garnier"), "Garnier Fructis Méthode Boucles")
        self.assertEqual(A.categorie_principale("Home Supplies | Home Supplies-Home Decor | Home Supplies-Towels"), "Home Supplies")

    def test_filtrage_des_recoupements(self):
        ventes = [{"title": "Brosse lissante LANDOT neuve", "soldPrice": "30"}, {"title": "Coffret de Noël thés", "soldPrice": "99"}]
        self.assertEqual([v["soldPrice"] for v in A.garder_ventes(ventes, "LANDOT")], ["30"])
        pubs = [{"platform": "meta", "advertiserName": "Landot Beauty"}, {"platform": "meta", "advertiserName": "Sébastien Roland Jean LANDOT"},
                {"platform": "meta", "advertiserName": "Seymouri", "landingUrl": "https://seymouri.com/products/landot-brush"}]
        self.assertEqual([x["advertiserName"] for x in A.garder_pubs(pubs, "LANDOT")], ["Landot Beauty", "Seymouri"])
        self.assertEqual(A.garder_pubs(pubs, ""), [])

    def test_recherche_precise_et_amazon(self):
        t = "[medicube Officiel] Sérum raffermissant NAD+ EGF | Sérum avec NAD+, EGF & extrait de collagène | K Beauty (30 ml)"
        self.assertEqual(A.mots_distinctifs(t, "medicube"), ["NAD", "EGF"])
        self.assertEqual(A.recherche_precise(t, "medicube"), "medicube NAD EGF")
        self.assertEqual(A.recherche_precise("LANDOT Brosse électrique lissante 2 en 1 pour cheveux", "LANDOT"), "LANDOT Brosse électrique")
        pubs = [{"landingUrl": "https://www.amazon.fr/dp/B0DGTMR754?maas=1"}, {"landingUrl": "https://www.amazon.fr/dp/B0DGTMR754"},
                {"landingUrl": "https://www.amazon.fr/medicube-PDRN/dp/B0GS8YKMN3"}, {"landingUrl": "https://www.amazon.com/dp/B000000000"},
                {"landingUrl": None}]
        self.assertEqual(A.asins_des_pubs(pubs), ["B0DGTMR754", "B0GS8YKMN3"])
        bon = {"titre": "medicube NAD+ EGF Firming Serum 30ml, sérum raffermissant coréen", "prix_neuf": 24.9, "asin": "B1"}
        autre = {"titre": "medicube PDRN Pink Collagen Jelly Cream 100ml", "prix_neuf": 19.9, "asin": "B2"}
        faux = {"titre": "Les 2 Marmottes Coffret Cadeau de Noël Contes de Thés", "prix_neuf": 19.95, "asin": "B3"}
        self.assertEqual(A.choisir_amazon(t, [autre, bon, faux, None, {"erreur": "x"}], "medicube")["asin"], "B1")
        self.assertIsNone(A.choisir_amazon(t, [autre], "medicube"))          # même marque, autre produit
        self.assertIsNone(A.choisir_amazon(t, [faux], "medicube"))           # la marque manque
        self.assertIsNone(A.choisir_amazon(t, [bon, dict(bon, asin="B9")], "medicube"))  # égalité : on ne tranche pas
        self.assertEqual(A.ressemblance(t, faux["titre"], ""), 0)

    def test_lecture_et_gain(self):
        p = A.lire_produit(ligne("LANDOT Brosse lissante", 1823, 46.2, 10, 15.03))
        self.assertEqual(p["gain_par_vente_usd"], 4.62)
        self.assertEqual(p["commissions_totales_usd"], round(1823 * 46.2 * 0.10))
        self.assertEqual(p["part_video_pct"], 90)
        self.assertIsNone(A.lire_produit({"message": "notice sans produit"}))
        self.assertIsNone(A.lire_produit({"title": "x", "unitsSold": "?", "avgSellingPrice": 1, "commissionRatePercent": 10}))

    def test_filtres(self):
        self.assertEqual(A.retenu(A.lire_produit(ligne("AYAT 50ML", 9302, 0.33, 10)), FILTRES)[0], False)
        self.assertEqual(A.retenu(A.lire_produit(ligne("Pinceaux teint", 2020, 20.21, 5, -37)), FILTRES)[1], "ventes en recul")
        self.assertEqual(A.retenu(A.lire_produit(ligne("Garnier Fructis", 5082, 6.84, 10)), FILTRES)[1], "gain par vente trop faible")
        self.assertTrue(A.retenu(A.lire_produit(ligne("LANDOT Brosse", 1823, 46.2, 10)), FILTRES)[0])

    def test_finalistes_varient_categories_et_marques(self):
        produits = [A.lire_produit(x) for x in [
            ligne("[medicube Officiel] Sérum NAD+", 4748, 17.33, 10),
            ligne("[medicube Officiel] Duo Rice Peel Shot", 2011, 35.35, 10),
            ligne("LANDOT Brosse lissante", 1823, 46.2, 10),
            ligne("Poêle antiadhésive 28 cm", 900, 25, 12, cat="Home Supplies"),
            ligne("Circuit voitures", 700, 30, 10, cat="Toys & Hobbies"),
        ]]
        f = A.choisir_finalistes(produits, FILTRES, 3)
        self.assertEqual(len(f), 3)
        self.assertEqual(len({p["categorie"] for p in f}), 3)
        self.assertEqual(len({p["marque"].lower() for p in f}), 3)
        # une seule catégorie disponible : on complète en variant seulement les marques
        f2 = A.choisir_finalistes(produits[:3], FILTRES, 3)
        self.assertEqual([p["marque"] for p in f2], ["LANDOT", "medicube"])

    def test_deux_classements_bingo_et_ordre(self):
        P = lambda *a, **k: A.lire_produit(ligne(*a, **k))  # noqa: E731
        landot, serum = P("LANDOT Brosse lissante", 1823, 46.2, 10, 15, lien="L"), P("[medicube Officiel] Sérum NAD+", 4748, 17.33, 10, 48, lien="S")
        monte = P("ZETA Lampe", 400, 30, 10, 300, cat="Home Supplies", lien="Z")
        monte2 = P("Tapis de bain", 300, 20, 10, 150, cat="Home Supplies", lien="T")
        tous = A.fusionner({"plus_vendus": [landot, serum], "hausses": [dict(serum), monte, monte2]})
        self.assertEqual(len(tous), 4)
        par = {p["lien"]: p for p in tous}
        self.assertTrue(par["S"]["bingo"])
        self.assertEqual(par["S"]["listes"], ["plus_vendus", "hausses"])
        self.assertEqual((par["L"]["bingo"], par["Z"]["listes"]), (False, ["hausses"]))
        self.assertIn("BINGO", A.trouve_par(par["S"]))
        self.assertEqual(A.trouve_par(par["Z"]), "classement des plus fortes hausses")
        # tourniquet : un bingo, une hausse, un plus vendu, puis on recommence (ici il ne reste qu'une hausse)
        self.assertEqual([p["lien"] for p in A.choisir_finalistes(tous, FILTRES, 4)], ["S", "Z", "L", "T"])
        self.assertEqual([p["lien"] for p in A.choisir_finalistes(tous, FILTRES, 2)], ["S", "Z"])

    def test_etiquettes_promo_et_lives(self):
        self.assertEqual(A.marque_fiable("[EXCLUSIVITÉ LIVE] medicube Routine PDRN Éclat"), "")
        self.assertEqual(A.marque_fiable("[EXCLUSIVITÉ LIVE] [medicube Officiel] Routine PDRN"), "medicube")
        self.assertEqual(A.marque_fiable("【Black Friday】GaaliShop | Dalles PVC"), "")
        self.assertEqual(A.marque_fiable("[medicube Officiel] Sérum"), "medicube")
        self.assertEqual(A.marque("[EXCLUSIVITÉ LIVE] medicube Routine"), "medicube")
        live = A.lire_produit(ligne("[EXCLUSIVITÉ LIVE] medicube Routine PDRN", 77, 151.82, 10, 529))
        self.assertEqual(A.retenu(live, FILTRES), (False, "réservé aux lives"))

    def test_classement_paye_une_fois_par_jour(self):
        v2 = {"jour": "16/11/2026", "classements": {"plus_vendus": [{"lien": "a"}], "hausses": []}}
        self.assertEqual(A.deja_lus(v2, "16/11/2026", "plus_vendus"), [{"lien": "a"}])
        self.assertIsNone(A.deja_lus(v2, "16/11/2026", "hausses"))
        self.assertIsNone(A.deja_lus(v2, "17/11/2026", "plus_vendus"))
        v1 = {"quand": "15/11/2026 à 20 h 54", "tous": [{"lien": "b"}]}
        self.assertEqual(A.deja_lus(v1, "15/11/2026", "plus_vendus"), [{"lien": "b"}])
        self.assertIsNone(A.deja_lus(v1, "15/11/2026", "hausses"))
        self.assertIsNone(A.deja_lus(None, "15/11/2026", "plus_vendus"))
        # un réglage qui change (plancher de chiffre d'affaires) invalide le classement du jour
        r = {"tri": "revenueGrowth", "revenu_min_usd": 1500}
        v3 = {"jour": "16/11/2026", "classements": {"hausses": [{"lien": "h"}], "plus_vendus": [{"lien": "a"}]}, "reglages": {"hausses": r}}
        self.assertEqual(A.deja_lus(v3, "16/11/2026", "hausses", r), [{"lien": "h"}])
        self.assertIsNone(A.deja_lus(v3, "16/11/2026", "hausses", dict(r, revenu_min_usd=3000)))
        self.assertIsNone(A.deja_lus({"jour": "16/11/2026", "classements": {"hausses": [{"lien": "h"}]}}, "16/11/2026", "hausses", r))
        self.assertEqual(A.deja_lus(v3, "16/11/2026", "plus_vendus", {"tri": "unitsSold"}), [{"lien": "a"}])  # ancien relevé sans réglages

    def test_moins_de_ventes_exigees_pour_les_hausses(self):
        f = dict(FILTRES, ventes_min_hausses=50)
        shark = A.lire_produit(ligne("Brosse Shark Smooth", 173, 66.87, 5, 389))
        self.assertEqual(A.retenu(shark, f)[1], "trop peu de ventes")
        self.assertTrue(A.retenu(dict(shark, listes=["hausses"]), f)[0])
        self.assertFalse(A.retenu(dict(shark, listes=["hausses"], ventes_7j=20), f)[0])

    def test_lien_qui_ouvre_l_appli(self):
        bon = "https://www.tiktok.com/view/product/1729922914496059620"
        self.assertEqual(A.lien_appli("https://shop.tiktok.com/fr/pdp/1729922914496059620"), bon)
        self.assertEqual(A.lien_appli("https://shop.tiktok.com/fr/pdp/manteau-bloom/1729922914496059620?x=1"), bon)
        self.assertEqual(A.lien_appli(bon), bon)
        self.assertEqual(A.lien_appli("https://exemple.fr/page"), "https://exemple.fr/page")
        self.assertEqual(A.lien_appli(None), "")
        p = A.lire_produit(ligne("LANDOT Brosse", 1823, 46.2, 10, lien="https://shop.tiktok.com/fr/pdp/1729506070096550618"))
        self.assertEqual(p["lien"], "https://www.tiktok.com/view/product/1729506070096550618")

    def test_resumes(self):
        e = A.resume_ebay([{"soldPrice": "213.90", "soldCurrency": "EUR"}, {"soldPrice": "230.00"}, {"soldPrice": None}])
        self.assertEqual((e["nb"], e["min"], e["max"], e["mediane"]), (2, 213.9, 230.0, 221.95))
        self.assertIsNone(A.resume_ebay([]))
        p = A.resume_pubs([{"platform": "meta", "daysRunning": "151", "advertiserName": "Medicube", "landingUrl": "https://www.amazon.fr/dp/X"},
                           {"platform": "meta", "daysRunning": 5, "advertiserName": "Medicube"}, {"message": "notice"}])
        self.assertEqual((p["nb"], p["plus_longue_jours"], p["depuis_30j_ou_plus"], p["vers_amazon"], p["annonceurs"]), (2, 151, 1, 1, ["Medicube"]))

    def test_rapport_ecrit_et_echappe(self):
        cfg = json.load(open(os.path.join(RACINE, "config/affiliation_tiktok.json"), encoding="utf-8"))
        tous = [A.lire_produit(ligne('LANDOT <script>alert(1)</script> Brosse', 1823, 46.2, 10)),
                A.lire_produit(ligne("AYAT 50ML", 9302, 0.33, 10))]
        fin = A.choisir_finalistes(tous, cfg["filtres"], 3)
        fin[0].update({"marque_sure": "LANDOT", "recherche": "LANDOT Brosse", "ebay": None, "ebay_lu": True, "pubs": None,
                       "pubs_lu": True, "pubs_terme": "LANDOT", "amazon": None})
        ancien = A.F_HTML
        with tempfile.TemporaryDirectory() as d:
            A.F_HTML = os.path.join(d, "r.html")
            try:
                A.rapport(tous, fin, cfg, 0.93, 0.412, "15/11/2026 à 21 h 00")
                page = open(A.F_HTML, encoding="utf-8").read()
            finally:
                A.F_HTML = ancien
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("aucune vente trouvée sur ebay.fr", page)
        self.assertIn("0,412 $", page)
        self.assertIn("Trouvé par : robot TikTok Shop (Apify)", page)
        self.assertTrue(A.message_telegram(fin, 0.93, 2).startswith("<b>Affiliation TikTok Shop</b>"))
        self.assertIn("Prix de vente moyen : 46,20 $ (≈ 42,97 €)", A.message_telegram(fin, 0.93, 2))
        self.assertIn("Prix de vente moyen</th><td><b>46,20 $ (≈ 42,97 €)</b>", page)
        sans = dict(fin[0], marque_sure="", titre="Manteau bloom")
        self.assertIn("non recoupé : produit sans marque identifiable", A.carte(sans, 0.93))
        self.assertIn("pas de marque identifiable", A.message_telegram([sans], 0.93, 2))


if __name__ == "__main__":
    unittest.main()
