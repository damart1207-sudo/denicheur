# Rebifftout : poste de contrôle local

## Lancer

Depuis un checkout complet de la branche de correction, avec Python 3.10 ou plus :

- Windows : double-cliquer sur `LANCER_PILOTE.bat`.
- Tous systèmes : `python saas/pilote.py --ouvrir`.
- Sans ouvrir le navigateur : `python saas/pilote.py`.
- Classement eBay : `python saas/pilote.py --canal ebay --objectif 20 --ouvrir`.

Le rapport est créé dans `data/test/pilote.html`, dossier déjà ignoré par Git. Il s'ouvre comme un fichier local et ne nécessite ni serveur ni installation supplémentaire. Il ne met pas à jour les données du dépôt : régénérer après une nouvelle collecte. Ne pas publier ce rapport interne sur la vitrine client.

## Ce qui fonctionne

- Charge les alertes existantes, recalcule les marges et le prix minimum pour atteindre l'objectif.
- Sépare coût prouvé récemment et coût historique estimé. Les simples statuts « validé » et anciennes marges ne sont pas utilisés comme preuve.
- Signale les références alphanumériques Keepa différentes ou incomplètes. Ce contrôle conservateur aide au tri ; ce n'est pas un rapprochement produit complet.
- Recherche, filtre, sélection de dix pistes, export CSV de la sélection et des blocages.
- Simulateur avec total fournisseur livré, total encaissé client, canal, objectif, frais mensuels et volume de ventes prévu.
- Aucune API, IA, notification, commande, publication ou souscription déclenchée par ce rapport. Les liens marchands s'ouvrent seulement à la demande.

Le classement utilise des hypothèses de prix de revente historiques. Un bon résultat signifie « à vérifier », jamais « acheter ». Il faut encore confirmer l'état, les ventes conclues comparables et l'éligibilité du canal. Les règles de frais doivent correspondre au régime et au compte réels. Le temps de travail n'est pas valorisé automatiquement.

La sélection n'est pas enregistrée automatiquement : exporter le CSV avant fermeture. Les simulations modifient uniquement l'écran, jamais le JSON des alertes. Le rapport n'intègre pas une base de commandes, une gestion de stock, un encaissement ou un suivi de retours.

## Sources et coûts consultés le 06/11/2026

| Source | Utilité | Décision pour le pilote |
| --- | --- | --- |
| eBay Product Research | Prix réellement payés, offres acceptées incluses, historique jusqu'à trois ans | Gratuit pour les vendeurs ayant accès au Seller Hub ; utiliser la consultation humaine et relever les comparables. Aucun accès API à ces données n'est présumé. |
| API eBay Browse existante | Annonces en cours | Comparer l'offre concurrente, sans la présenter comme une preuve de ventes conclues. |
| Keepa existant | Historique et données Amazon | Vérifier la référence exacte et exploiter l'accès déjà configuré. Les chutes de classement sont des signaux, pas un décompte certifié des ventes. Prix d'un nouveau forfait non confirmé, aucune souscription recommandée à l'aveugle. |
| Apify | Collecte ciblée de pages marchandes | Le tarif public Starter est de 19 USD/mois, avec 19 USD de consommation incluse puis consommation supplémentaire. Ce montant n'est pas un plafond. Le prix et les coûts de chaque Actor doivent aussi être vérifiés. Pas de nouvel abonnement souscrit. |

Sources :
- https://www.ebay.com/sellercenter/growth/ebay-research-tools
- https://www.ebay.com/help/selling/selling-tools/research?id=4853
- https://keepa.com/api-docs/plans-tokens.html
- https://apify.com/pricing

## Ce qui reste à activer ou démontrer

1. Rapprocher les dépenses avec les comptes fournisseurs ; mettre à jour ou arrêter les anciens workers, puis terminer la migration du registre. Le verrou de la nouvelle version ne stoppe pas l'ancien code en production.
2. Tester les collecteurs avec les accès existants et des destinations de livraison autorisées, sans acheter ni lever les blocages sur des données absentes.
3. Valider quelques opérations complètes : produit exact, coût livré, demande réelle, frais, éligibilité du canal. Mesurer le résultat après vente avant d'automatiser un achat.
4. Définir un plafond mensuel explicite avant tout nouvel engagement payant. Ne pas confondre consommation API et coût d'abonnement.
5. Pour la vente directe client : terminer le parcours commande, stock, paiement, suivi, retours et les informations réelles de l'exploitant. Ce lot ne permet pas d'encaisser automatiquement.

Les tests hors réseau couvrent les coûts, le blocage sur preuves absentes, les budgets concurrents et le poste de contrôle. Le lanceur Windows n'a pas été exécuté sur le PC de l'utilisateur.

## Rapport généré sur GitHub

Le workflow `Vérification sans appels payants` produit maintenant un fichier à télécharger nommé `rebifftout-pilote` après les tests. Il utilise le code de la branche testée et lit uniquement `data/alertes.json` depuis la dernière révision de `main`, sans exécuter le code de cette seconde copie. Le rapport affiche sa date de génération. Le fichier est conservé sept jours dans les artefacts de l'exécution GitHub Actions.

Sur une mise à jour de la proposition, les tests et cette génération se lancent automatiquement. La génération du pilote ne déclenche pas de nouvelle collecte fournisseur : elle examine les alertes présentes sur `main`. Ce n'est pas encore un service qui tourne en permanence, ni un déploiement de la nouvelle collecte en production. Aucun secret fournisseur n'est fourni à ce workflow et ses permissions restent en lecture seule. Un compte GitHub autorisé peut être requis pour télécharger l'artefact.

Les références composées des comparateurs et de la recherche Keepa conservent leurs suffixes : `A620M-E` ne correspond plus à `A620M-B`. Les fiches Keepa demandées par EAN/UPC ou ASIN sélectionnent l'identifiant exact dans la réponse ; un autre produit, une ambiguïté ou une liste d'identifiants malformée sont refusés. Cela élimine cette classe de faux rapprochements, sans prouver à lui seul l'état, la couleur ou les accessoires. Les anciennes alertes ne sont pas réécrites silencieusement.
