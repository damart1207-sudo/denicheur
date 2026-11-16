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

A.F_RESERVE = os.path.join(tempfile.mkdtemp(), "affiliation_comparaison.json")  # jamais le vrai compteur pendant les tests

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

    def test_comparaison_avec_les_marchands_francais(self):
        # offres réelles relevées sur Google Shopping le 15/11/2026
        O = lambda t, p, m="Amazon.fr - Seller": {"titre": t, "prix": p, "marchand": m, "devise": "EUR", "lien": "https://x"}  # noqa: E731
        t_landot = "LANDOT Brosse électrique lissante 2 en 1 pour cheveux, peigne lissant et boucleur anti-emmêlement"
        self.assertEqual(A.requete_comparaison(t_landot, "LANDOT"), ("LANDOT Brosse électrique lissante", "meme_produit"))
        self.assertEqual(A.requete_comparaison("Manteau bloom", ""), (None, "titre_vague"))
        self.assertEqual(A.requete_comparaison("Gamme jaune poussin métisse", ""), (None, "titre_vague"))
        self.assertEqual(A.requete_comparaison("100 blocs de construction magnétiques – Jeu créatif STEM pour enfants", "")[1], "equivalents")
        landot = [O("Landot Brosse Lissante Chauffante Ionique 2 en 1 Lisseur", 47.99), O("LANDOT Brosse Lissante, 12 Temp 120-230°C", 45.99),
                  O("Brosse Lissante Remington Keratin Protect", 45.99, "Amazon.fr"),            # autre marque
                  O("LANDOT Boucleur Lisseur 2 en 1, Plaques Céramiques", 42.99),                # même marque, autre produit
                  O("LANDOT Brosse électrique lissante 2 en 1 pour cheveux,", 42.00, "Leboncoin")]  # occasion
        c = A.comparer_offres(landot, t_landot, "LANDOT", "meme_produit", 41.80)
        self.assertEqual((c["type"], c["nb"], c["min"], c["max"], c["ecart_eur"]), ("meme_produit", 2, 45.99, 47.99, 4.19))
        self.assertIn("même produit à partir de 45,99 € chez Amazon.fr - Seller (2 offres, jusqu'à 47,99 €)", A.texte_comparaison(c))
        self.assertIn("soit 4,19 € de moins", A.texte_comparaison(c))
        plus_cher = A.comparer_offres(landot, t_landot, "LANDOT", "meme_produit", 55.0)
        self.assertIn("PLUS CHER", A.texte_comparaison(plus_cher))
        t_blocs = "100 blocs de construction magnétiques – Jeu créatif STEM pour enfants"
        blocs = [O("VEVOR Construction Magnétique Enfant 100 Blocs Magnétiques", 20.14, "Darty"), O("Blocs Construction Magnétiques 100 Pièces", 39.99),
                 O("100 blocs de construction magnétiques jouets série pompier", 26.84, "Leroy Merlin"),
                 O("Jeu de construction magnetique SPRINGOS 2025", 18.99, "Cdiscount")]             # pas 100 blocs : écarté
        c = A.comparer_offres(blocs, t_blocs, "", "equivalents", 14.11)
        self.assertEqual((c["type"], c["nb"], c["min"], c["max"], c["mediane"]), ("equivalents", 3, 20.14, 39.99, 26.84))
        self.assertIn("produits équivalents (pas forcément le même)", A.texte_comparaison(c))
        # relevé réel du 15/11 (23 h 55) : un jeu de 80 pièces et un lot à 1 438,80 € faussaient la fourchette
        blocs2 = blocs + [O("HISHOPTOY Blocs de Construction magnétiques 80 pièces Enfants", 17.99), O("Lot 60 boîtes 100 blocs de construction magnétiques", 1438.80)]
        c2 = A.comparer_offres(blocs2, t_blocs, "", "equivalents", 14.11)
        self.assertEqual((c2["nb"], c2["min"], c2["max"]), (3, 20.14, 39.99))
        # trop peu d'offres proches : on n'affiche pas de fourchette
        sq = [O("6 PCS Crunchy Squishy Fun Box Asmr", 29.99), O("Dumpling Squishies Mystery Box", 40.0, "ubuy.fr")]
        c = A.comparer_offres(sq, "Coffret de Noël – 6 squishies à presser en forme de petits pains vapeur", "", "equivalents", 21.77)
        self.assertEqual(c["type"], "aucune")
        self.assertIn("aucune offre comparable", A.texte_comparaison(c))
        self.assertIn("titre trop vague", A.texte_comparaison({"type": "titre_vague"}))
        self.assertEqual(A.texte_comparaison(None), "")

    def test_equivalents_situes_par_rapport_au_prix_median(self):
        base = {"type": "equivalents", "min": 19.88, "max": 94.98, "mediane": 44.99, "nb": 15, "moins_cher": {"marchand": "Amazon.fr", "prix": 19.88}}
        self.assertIn("dans les prix du marché", A.texte_comparaison(dict(base, prix_tiktok_eur=44.47, ecart_eur=-24.59)))
        self.assertNotIn("PLUS CHER", A.texte_comparaison(dict(base, prix_tiktok_eur=44.47, ecart_eur=-24.59)))
        self.assertIn("de moins que le prix médian", A.texte_comparaison(dict(base, prix_tiktok_eur=30.0, ecart_eur=-10.12)))
        self.assertIn("de plus que le prix médian", A.texte_comparaison(dict(base, prix_tiktok_eur=60.0, ecart_eur=-40.12)))

    def test_reserve_de_la_comparaison(self):
        """0,02 $ par jour au-dessus du plafond, seulement pendant la comparaison, et jamais deux fois le même jour."""
        vus = []
        ancien, fichier = A.shopping.chercher, A.F_RESERVE
        A.F_RESERVE = os.path.join(tempfile.mkdtemp(), "r.json")
        base = A.dataforseo.plafond_du_jour()
        A.shopping.chercher = lambda q, pays="FR", **k: (vus.append(round(A.dataforseo.plafond_du_jour() - base, 4)) or {x: [] for x in q})
        try:
            cfg = {"comparaison": {"actif": True, "mots_min_titre": 6, "reserve_usd": 0.004}}
            neufs = lambda: [A.lire_produit(ligne("LANDOT Brosse électrique lissante 2 en 1", 1823, 46.2, 10)),
                             A.lire_produit(ligne("NYX Rouge à lèvres mat longue tenue", 900, 9, 10)),
                             A.lire_produit(ligne("medicube Sérum raffermissant collagène", 900, 19, 10))]
            A.comparer(neufs(), 0.9, cfg)
            self.assertEqual(vus, [0.004])                                # 3 recherches = 0,006 $, réserve limitée à 0,004 $
            self.assertEqual(A.dataforseo.plafond_du_jour(), base)        # la réserve disparaît après la comparaison
            self.assertEqual(A.reserve_restante(cfg["comparaison"]), 0.0)
            A.comparer(neufs(), 0.9, cfg)
            self.assertEqual(vus[-1], 0.0)                                # déjà prise aujourd'hui : plus rien au-dessus du plafond
            self.assertEqual(A.reserve_restante(cfg["comparaison"], jour="2099-01-01"), 0.004)   # un autre jour : réserve entière
            self.assertEqual(A.reserve_restante({}), 0.0)                 # sans réglage : aucune réserve
        finally:
            A.shopping.chercher, A.F_RESERVE = ancien, fichier

    def test_comparer_ne_cherche_que_ce_qui_manque(self):
        demandes = []
        ancien = A.shopping.chercher
        A.shopping.chercher = lambda q, pays="FR", **k: (demandes.append(list(q)) or {q[0]: [{"titre": "LANDOT Brosse Lissante", "prix": 45.99, "marchand": "Amazon.fr", "devise": "EUR"}]})
        try:
            cfg = {"comparaison": {"actif": True, "mots_min_titre": 6}}
            f = [A.lire_produit(ligne("LANDOT Brosse électrique lissante 2 en 1", 1823, 46.2, 10)), A.lire_produit(ligne("Manteau bloom", 473, 27, 13)),
                 dict(A.lire_produit(ligne("NYX Rouge", 900, 9, 10)), comparaison={"type": "aucune"})]
            self.assertEqual(A.comparer(f, 0.9, cfg), 1)
            self.assertEqual(demandes, [["LANDOT Brosse électrique lissante"]])
            self.assertEqual((f[0]["comparaison"]["type"], f[1]["comparaison"]["type"], f[2]["comparaison"]["type"]), ("meme_produit", "titre_vague", "aucune"))
            self.assertEqual(A.comparer(f, 0.9, cfg), 0)          # plus rien à chercher : aucun appel
            self.assertEqual(len(demandes), 1)
            self.assertEqual(len(f[0]["comparaison"]["offres"]), 1)   # offres enregistrées
            f[0]["comparaison"]["v"] = 1                               # tri des offres modifié : recalcul gratuit, sans appel
            self.assertEqual(A.comparer(f, 0.9, cfg), 1)
            self.assertEqual((len(demandes), f[0]["comparaison"]["v"]), (1, A.VERSION_COMPARAISON))
            vieux = {"type": "equivalents", "min": 17.99, "max": 1438.8, "mediane": 25.99, "nb": 14}
            h = [dict(A.lire_produit(ligne("100 blocs de construction magnétiques – Jeu créatif STEM pour enfants", 557, 15.59, 8)), comparaison=vieux)]
            A.comparer(h, 0.9, cfg)                                    # fourchette aberrante sans offres enregistrées : redemandée
            self.assertEqual(len(demandes), 2)
            A.shopping.chercher = lambda q, pays="FR", **k: {}     # budget atteint : marqué « non lu », réessayé au lancement suivant
            g = [A.lire_produit(ligne("LANDOT Brosse électrique lissante 2 en 1", 1823, 46.2, 10))]
            self.assertEqual(A.comparer(g, 0.9, cfg), 0)
            self.assertEqual(g[0]["comparaison"]["type"], "non_lu")
        finally:
            A.shopping.chercher = ancien

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
