# Le Dénicheur / Rebifftout — dossier complet du projet

*Rédigé le 05/11/2026 pour briefer une autre IA (ChatGPT) ou un collaborateur. Tout ce qui suit est l'état réel au 05/11, avec ce qui marche, ce qui est en test et ce qui reste à construire.*

---

## 1. En une phrase

David Martinez (micro-entrepreneur français, salarié par ailleurs) construit un système automatisé qui **trouve des produits vendus nettement moins cher que le prix le plus bas du marché français** (erreurs de prix, promos non repérées, écarts entre pays, liquidations, occasion sous-cotée) pour **les revendre avec marge** — sur Vinted/eBay, et surtout via son propre site **rebifftout.fr**, avec un modèle inédit : **le client dit ce qu'il veut et le prix maximum qu'il accepte, les robots chassent, il ne paie que quand c'est trouvé** (« Moins cher que prévu »).

## 2. Objectifs chiffrés

- **Objectif mensuel : 600 € nets** = 300 € pour rembourser l'investissement (outils) + 300 € de bénéfice. Compté net : après achat du produit, port, frais Stripe (~1,5 % + 0,25 €) et cotisations micro-entreprise (~12-13 % du chiffre d'affaires).
- Soit environ **20 ventes à 30 € nets** ou **30 ventes à 20 € nets** par mois.
- Premier mois visé : 27 novembre → 27 décembre 2026 (période de Noël).
- Capital de départ : 500 à 700 €. Budget outils : ~120-155 €/mois.
- **Règles absolues de David** : ne jamais lui faire dépenser d'argent inutilement (plafonds, garde-fous, jamais de tâche payante laissée tourner sans surveillance) ; ne jamais annoncer qu'un outil « est en place » avant de l'avoir vérifié en conditions réelles avec des chiffres ; ne jamais lui envoyer un rapport vide ou contenant une excuse technique — réparer et relancer d'abord.

## 3. L'équipe de dénicheurs (robots)

| Nom | Rôle |
|---|---|
| **Idéfix (A)** | Trouve les écarts de prix : bons plans (réseau Pepper 12 pays : Dealabs, mydealz, hotukdeals, chollometro…), chaînes Telegram publiques d'erreurs de prix, prospectus de magasins, pages promos lues par le PC, radar Keepa. Alerte sur tout écart (ex. 100 € sur idealo, trouvé 50 €) sans attendre le volume de recherche. |
| **Amigo (B)** | La demande : les 150 produits les plus recherchés en France (volumes Google via DataForSEO), tendances, hypes étrangères (meilleures ventes Amazon US/JP/UK), classements du jour à 23 h 59 locale (USA, Japon, Royaume-Uni, Chine). Transmet une « liste de chasse » à Idéfix et au Chasseur. |
| **Chasseur (C)** | Sur le PC de David (Vinted, Leboncoin) : annonces de particuliers sous-cotées, annonces « invisibles » (fautes d'orthographe), vendeurs pressés ; relève les ventes eBay réellement conclues (prix payés). Annonces de plus de 7 jours écartées. |
| **Vinted inter-pays (D)** | Écarts de prix Vinted entre pays européens (en veille). |
| **Sourceur (E)** | Pour les « bingos » : distributeurs, grossistes, usines (Alibaba/1688), comment les concurrents s'approvisionnent, message de négociation prêt. Utile pour les achats groupés. |

## 4. La chaîne de décision (règles de David)

1. **Gros volume de recherche** (Google, Amazon) **ou** écart de prix flagrant.
2. **Produit trouvé au prix le plus bas**, comparé au **prix le plus bas en France** (comparateurs, Google Shopping).
3. **Concurrence** : ≥ 10 vendeurs dont un gros site au même prix → on passe ; 5-9 → seulement si ≥ 15 % moins cher ; ≤ 4 et moins cher → bingo.
4. **Fourchette d'occasion** réellement payée (eBay vendus, Vinted, Leboncoin).
5. **Comparer à état égal** : neuf de professionnel contre neuf de professionnel uniquement ; occasion contre occasion uniquement ; reconditionné contre reconditionné, signalé comme tel.
6. **Même produit exact** : même marque, modèle, variante (taille, capacité, couleur), **même quantité dans le lot** (piège vu le 05/11 : lot de 2 roues gonflables comparé à un lot de 8 roues pleines), même état. Contrôle mécanique (quantité, caractéristiques opposées, dimensions, capacités) puis verdict IA.
7. **Prix revérifié sur la fiche du marchand** avant toute alerte (données structurées de la page, ou prix principal affiché ; jamais une carte voisine).

**Feux :**
- 🟢 **Vert** = l'affaire tient : bénéfice ≥ 20 €, ≥ 15 % sous le prix France, prix contrôlé sur la fiche, aucun mauvais signal (trop de concurrents, revente au-dessus des prix d'occasion).
- 🟠 **Orange** = un vrai problème bloque (écrit en clair). Les informations manquantes (concurrence, volume, occasion) sont « à compléter » et **ne bloquent pas** le vert.
- 🔴 **Rouge** = perte, bénéfice < 10 € ou concurrence trop forte : jamais envoyé.

## 5. Le modèle de vente « Moins cher que prévu » (rebifftout.fr)

Nom du service retenu : **« Moins cher que prévu »** (Rebifftout reste la marque).

**Parcours client :**
1. Le visiteur tape un produit. **Analyse en direct (10-20 s)** : identification du produit exact (IA), prix actuel et historique 90 jours sur Amazon FR/DE/IT/ES/US/JP (Keepa), eBay, Google Shopping. Les sites où l'on chasse ne sont **jamais** montrés ; seul le **prix public le plus bas en France** est affiché.
2. Le site propose des **paliers de prix réalistes**, avec leurs chances (« 419 € : élevées », « 389 € : moyennes », « 350 € : rare, vu 1 fois en 90 jours ») — le client ne peut pas taper un prix jamais vu (PS5 à 100 €). Produit rare : analyse approfondie sous 24 h.
3. Il donne **deux prix max** : neuf, et occasion/reconditionné (l'un ou l'autre ou les deux). Il choisit comment être prévenu : **e-mail ou Telegram**. **Pas de carte, pas de compte, pas d'engagement.** Durée : 30 jours max, puis la demande s'arrête seule (message honnête : « plus bas vu ce mois-ci : X €, on continue à ce prix ? »).
4. Les robots chassent (toutes les sources + surveillance Keepa déclenchée seulement si rien n'est trouvé à l'analyse immédiate, arrêtée dès paiement/annulation/30 jours).
5. **Trouvé** : le client reçoit l'offre, valable 12 h, avec lien de paiement Stripe. Si neuf ET occasion trouvés : les deux sont proposés ; sinon seulement ce qui est trouvé. Pour l'occasion : prix + **photos** + état détaillé réécrit (usure, défauts, accessoires), sans lien ni nom du site ; photos supplémentaires demandées au vendeur quand possible (introuvables par recherche d'image).
6. Il paie → David commande (ou commande automatique plus tard), **livraison directe chez le client** (dropshipping depuis la source, option « cadeau » sur Amazon pour ne pas montrer le prix ; point relais près du client pour l'occasion Vinted/Leboncoin). **Zéro stock, zéro capital avancé, un seul port.** Facture Rebifftout envoyée par e-mail. Si la source disparaît : remboursement intégral automatique.
7. **Délai affiché : nombre de jours seulement**, jamais la provenance. Douane hors UE toujours payée par nous à la commande.

**Prix client (règle de David) :** coût total = achat + TVA d'import (hors UE) + port + douane + frais Stripe + cotisations. Marge visée recalculée chaque jour pour atteindre les 600 € du mois : (reste à gagner) ÷ (ventes encore attendues). **Règle normale : le client paie son prix max.** **Gros écart** (surplus ≥ 2 × marge visée) : on garde la marge visée + une part du reste, le client paie moins que son max (remise = 30 % du reste avant objectif, 50 % après). Déclenchement seulement si marge nette ≥ 10 €. Plancher 10 € nets une fois l'objectif atteint.

**Extensions prévues :** enchère cachée (le prix max de chaque client est son enchère ; le produit va au plus offrant ; compteur « 3 personnes chassent ce produit »), achat immédiat à prix fixe quand plusieurs exemplaires sont disponibles, **achat groupé** (≥ 10 demandes sur le même produit → le Sourceur négocie auprès d'un grossiste, groupe ouvert sur le site avec compteur, remboursement automatique si incomplet).

**Trafic :** outil gratuit « est-ce que je paie trop cher ? » (prix France en direct) comme porte d'entrée ; pages produit automatiques avec données uniques (prix réels mis à jour chaque heure, 150 produits les plus recherchés) ; Google Merchant Center (fiches gratuites) ; bouton « me prévenir sur Telegram quand le prix baisse » sur chaque page ; parrainage (5 € pour deux) ; vidéos courtes automatiques sans visage (David veut rester anonyme) ; chaîne Telegram publique (3-5 affaires vérifiées par jour) ; annuaires et échanges de chaînes ; communautés de bons plans sans autopromotion ; publicité en dernier, plafonnée.

**Règles des plateformes vérifiées :** Leboncoin interdit tout lien/redirection externe et refuse le neuf vendu par des pros dans la plupart des catégories → Leboncoin = occasion seulement. Vinted : dropshipping interdit (il faut posséder l'article). eBay : dropshipping autorisé seulement depuis un grossiste, pas depuis un autre détaillant. Dealabs : autopromotion interdite. Amazon : pas de Prime pour revendre. Ne jamais inviter les acheteurs Vinted/eBay vers l'extérieur (risque de suspension).

## 6. Ce qui existe et tourne (état au 05/11)

- **Dépôt GitHub** `damart1207-sudo/denicheur` (Python). Workflow GitHub Actions : veille toutes les heures (tours de 10 min), 3 passages complets par jour lancés par une tâche planifiée (5 h, 13 h, 18 h Paris) + outils de test (`outils/*.py`, lancés avec l'entrée `outil=`).
- **Telegram** (bot privé « Rebifftout Dénicheur », secrets posés, testé le 04/11) : alertes au fil de l'eau avec **fiche de décision complète** (prix le plus bas, neuf ailleurs, concurrence, recherches Google, ventes Amazon 30 j, occasion, prix d'achat max, canal de revente, bénéfice net, probabilité de vendre en 7 jours, contrôle du prix sur la fiche, liens) ; résumé de chaque passage + rapport HTML en pièce jointe ; chaque nuit : « les plus recherchés en France » et « hype étrangère du jour » (volumes FR et pays d'origine, ventes par site, achat le moins cher rendu en France, double hausse ventes+recherches → analyse approfondie) ; classements du jour USA/Japon/UK (Amazon, photo à 23 h 59 locale) et Chine (SMZDM, JD.com en cours).
- **Rapport HTML** `data/rapport_david.html` à onglets (affaires, alertes 24 h, radar, hype, bingo, plus recherchés, arbitrage Europe, sourceur, chasseur, demande par pays, outils), tri et filtres, chaque affaire signée par son dénicheur.
- **Keepa** (abonnement, 20 jetons/min, tous utilisés chaque jour) : radar des baisses FR/DE/IT/ES, arbitrage Europe, hype US/JP, étagère de produits, identification ASIN/EAN, vendeurs, ventes (monthlySold, salesRankDrops), classements. Réserve de 700 jetons avant chaque classement.
- **DataForSEO** (plafond 1 $/jour, dépassement exceptionnel autorisé le 05/11) : volumes Google, Google Trends, **Google Shopping** (recherche produit → fiche produit exacte → vendeurs, prix + port, 0,002 $/requête).
- **Apify** (plafond 35 $/mois) : idealo, Vinted/Leboncoin revente réelle. **eBay API** (gratuit) : neuf/occasion, vendus. **Gemini** (vérification, mots-clés, sourcing, lecture de prospectus par image, verdict « même produit »).
- **PC de David** (Windows, Chrome piloté, hors écran, tâches planifiées : collecteur toutes les heures, chasseur toutes les 20 min ; mise à jour automatique du code à chaque envoi) : ~95 pages (magasins, ventes privées, outlets, occasion, enchères, classements) ; **prix lus en priorité dans les données intégrées de la page** (ManoMano : prix, prix « le + bas sur 30 j », vendeur, occasion), sinon cartes produit ; relecture de la fiche produit des produits remisés ≥ 30 % avant envoi ; méthode « onglet meilleures offres / Black Friday + long défilement » (ManoMano, Cdiscount, Rakuten) ; eBay « objets vendus ».
- **Prospectus de magasins** (Bonial) lus chaque nuit : grille d'offres structurée + 2 premières pages par Gemini ; non alimentaire ≥ 15 € ; testé le 05/11 (ex. Decathlon : doudoune The North Face 149,99 € au lieu de 249,99 €).
- **Chaînes Telegram publiques** lues sans compte (promorat, bonsplans).
- **Sites bloqués pour le cloud** (GitHub) : ManoMano, Cdiscount, Fnac/Darty, Carrefour, La Redoute, Tiendeo → lus par le PC.

## 7. Résultats des tests de méthode du 05/11 (données chiffrées uniquement, aucune lecture d'écran)

- Test 1 (baisses Keepa ≥ 30-40 % sur Amazon FR/DE) : 159 produits, 54 de marques sérieuses, **presque aucun vraiment moins cher que le marché** — une baisse par rapport à l'historique Amazon ≠ moins cher que le marché.
- Test 2/3 (20-60 produits les plus recherchés, Google Shopping, fiche produit exacte, vendeurs neufs sérieux) : **aucun écart ≥ 15 % entre marchands sérieux** — sur les produits stars, tout le monde s'aligne.
- Test 4 (39 produits Black Friday ManoMano vs marché français, même produit confirmé) : **1 bingo** (roue de diable 11,95 € contre 22,94 € chez Leroy Merlin, même modèle), les faux bingos (lot de 2 vs lot de 8, variantes, produits absents ailleurs) écartés.
- Conclusion : les vraies affaires sont **rares et dispersées** ; il faut passer **beaucoup de sources** au crible chaque jour avec une comparaison stricte, pas chercher « des centaines de -50 % ».

## 8. Reste à construire (ordre)

1. Appliquer le contrôle « même produit » et la comparaison Google Shopping à **toutes** les alertes et rapports (plus seulement aux tests).
2. **Boutique rebifftout.fr** (Hostinger PHP + Stripe en mode test d'abord) : page « Je cherche » avec analyse en direct, paliers, dépôt sans carte (e-mail/Telegram), liste de chasse branchée sur tous les dénicheurs, offre + paiement, suivi, CGV/mentions légales (SIREN affiché), page « comment on vérifie ».
3. Flux Google Merchant Center ; chaîne Telegram publique ; pages produit automatiques.
4. Sources encore à brancher : catalogues d'affiliation (Awin…) — inscription par David ; API AliExpress (clés de David, déjà existantes) ; Facebook Marketplace (compte dédié) ; Google Trends API officielle (demande) ; bibliothèque publicitaire Meta (vérification d'identité).
5. Serveur Hetzner (celui de Mibisou si place) pour remplacer GitHub Actions (horaires sautés, limites de durée) et recevoir les alertes Keepa.
6. Suivi achats/ventes sur Telegram (« acheté X à 60 € », « vendu X à 95 € » → progression vers 600 €), rédacteur d'annonces Vinted/eBay, compteur de marge dynamique.
7. Plus tard : enchère cachée, achats groupés, compte Amazon Pro (seulement si vente sur Amazon), navigateur cloud pour décharger le PC, 250 dénicheurs, SaaS.

## 9. Ce qu'il faut encore de David

- Accès Hostinger (hPanel/FTP) et clé Stripe **de test**.
- Clés AliExpress dans les secrets GitHub.
- Inscription Awin (éditeur, site rebifftout.fr) ; compte Facebook dédié ; vérification INPI de « Moins cher que prévu » ; vérifier avec l'URSSAF l'ajout de l'activité de vente de marchandises (activité déclarée : « exploitation de portails Internet ») ; Radar Lite chez Stripe avant janvier 2027.
- Comptes Vinted Pro et eBay ; compte Vinted/Leboncoin dédiés au robot (pas les comptes personnels).
- Vérifier les premiers bingos et signaler toute erreur (prix, produit, lot) : chaque cas réel sert à régler les filtres.

## 10. Leçons apprises (à ne pas répéter)

- Ne jamais lire un prix « à l'écran » (prix découpé 64/,90 lu 640,90 ; carte voisine ; mensualités). Toujours les données structurées, puis la fiche du marchand.
- Même Google Shopping peut être en retard sur le prix réel du marchand → la fiche du marchand a le dernier mot.
- Un « -76 % » sur un prix barré gonflé n'est pas une affaire ; seule la comparaison au marché compte.
- Comparer uniquement le même produit exact, à état égal et à quantité égale.
- Des cases vides ne doivent pas bloquer une bonne affaire ; un vrai problème, oui.
- Pas de dropshipping depuis un détaillant sur eBay/Amazon ; possible sur son propre site avec ses obligations (rétractation 14 j, garantie, retours).
