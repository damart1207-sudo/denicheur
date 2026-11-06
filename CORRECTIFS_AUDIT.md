# Correctifs prioritaires de l'audit Rebifftout

Base examinée : commit c6f06e7, 5 novembre 2026. Branche : fix/audit-rentabilite-verifications.

## Changements

- Calcul central des marges après commissions, frais du canal, prélèvements et provision d'incident. Les anciennes marges des alertes sont recalculées avant la fiche de décision.
- Hypothèses configurables dans config/regles.json : cotisations 12,3 %, versement libératoire 1 %, formation professionnelle 0,1 %, provision 3 EUR/commande. Ces hypothèses doivent correspondre au régime effectif. Les abonnements, autres charges et le temps de travail restent à déduire séparément. Le tarif Stripe configuré pour rebifftout est une hypothèse cartes standard EEE, pas un tarif universel.
- Lecteur strict du prix : produit principal identifiable par URL/identifiant ou canonique, EUR, offre en stock et sans ambiguïté. Aucun prix extrait d'un script quelconque, d'une offre agrégée ou d'une page de bons plans ne vaut confirmation.
- Tolérance de prix limitée à un centime ; une variation de plusieurs euros n'est plus assimilée à un arrondi.
- Le collecteur PC produit un reçu daté avec le lecteur strict. Le repli visuel ne permet plus de confirmer un prix.
- Identité produit : couleur prise en compte, unités normalisées, lot de 1 reconnu, cache IA renouvelé et expirant après 24 h, titres complets dans la clé. Une IA indisponible ne confirme pas l'identité.
- Barrière commune pour fiches, passages et site : prix récent/cohérent, même produit confirmé, livraison France et coût total explicitement confirmés. Les critères complémentaires de demande peuvent rester inconnus.
- Remplacement des probabilités non calibrées par des indicateurs qualitatifs de demande.
- Déduplication des liens publics ; promesse comparative limitée au périmètre des sources consultées.

## Contrat de données

Un booléen historique prix_verifie ne suffit plus. Un reçu PC preuve_prix doit contenir : prix_page, lien, devise=EUR, disponibilite=InStock, identite_confirmee=true, verifie_le (ISO 8601 avec fuseau).

Le contrôle final controle_prix contient statut=ok, prix_page, lien et verifie_le. Il est valable quinze minutes et doit correspondre au prix et à l'URL marchande de l'offre, paramètres de variante conservés.

Le champ meme_produit.meme doit valoir true après comparaison de l'offre et de sa référence. livraison_fr_confirmee et cout_total_confirme doivent être explicitement vrais après contrôle réel. La déduction ancienne de livraison à partir du seul domaine marchand ne remplit pas ces champs. Ne jamais les ajouter par défaut pour rétablir des cartes vertes.

Les offres historiques sans ces preuves restent des pistes internes. La vitrine peut donc être vide après reconstruction. Aucun stock ni livraison n'a été vérifié en direct pour cette livraison de code.

## Vérification sans dépense ni notification

Depuis la racine du dépôt :

```sh
python -m unittest discover -s tests -v
python -m compileall -q denicheur saas pc tests
```

Les tests n'appellent pas les fournisseurs, les IA ou Telegram. Ne pas utiliser les anciens scripts outils/test_*.py pour une vérification gratuite : certains appellent réellement des services.

## Application et retour arrière

Examiner le patch dans une copie du dépôt, puis appliquer avec git apply --check et git apply. Si des commits ont modifié les mêmes lignes depuis c6f06e7, réconcilier les changements avant toute application. Exécuter les commandes de vérification ci-dessus avant fusion. Tester ensuite le nouveau contrat avec une offre marchande réellement vérifiée.

Aucun changement en production, aucune modification des tâches PC et aucun appel payant n'ont été effectués pendant cette intervention. Le rollback consiste à revenir au commit précédent sur la branche de travail avant fusion ; éviter de rétablir silencieusement les anciennes marges comme si elles étaient nettes.

## Reste à traiter

- Alimenter les preuves de livraison/coût total pour chaque fournisseur et les revérifier au paiement.
- Valider les tarifs, frais d'import et taux effectifs ; le calcul d'import ancien n'a pas été refondu dans ce lot.
- Activer le registre partagé de budgets et mettre à jour tous les workers lors du basculement.
- Revoir l'éligibilité des canaux selon le produit, l'état et le mode d'approvisionnement (notamment Vinted et eBay).
- Construire le parcours commande/Stripe, réservation, retours et suivi de trésorerie.
- Renseigner les mentions légales avec les informations réelles de l'exploitant, préparer les documents commerciaux et les obligations d'occasion le cas échéant.

Ce lot n'est pas une validation juridique ni une autorisation de mise en vente automatique.

## Deuxième lot : réservations de budget concurrentes

Les dépenses DataForSEO et Apify sont maintenant réservées avant le POST. Un appel non autorisé par le registre n'est pas envoyé. Une réponse perdue/timeout conserve le montant réservé, sans relance automatique. DataForSEO rapproche le coût réel quand il est reçu ; un tarif supérieur à la réserve bloque le service jusqu'à examen. Un coût réel nul est bien pris en compte. Apify conserve le plafond de l'appel faute de facture détaillée dans le dataset.

Sur un seul hôte, le registre local est verrouillé entre processus et écrit par remplacement atomique. Sur GitHub Actions, le registre est partagé sur la branche `budget-api`, fichier `registre-budgets.json` ; la mise à jour conditionnelle sur la révision GitHub protège les réservations simultanées de runners distincts. Aucun repli sur un fichier local n'est autorisé en Actions. Le jeton automatique du workflow est transmis uniquement par variable d'environnement. Le registre ne contient ni clés ni données clients.

Avant activation des appels payants, créer la branche `budget-api` depuis une révision existante, puis la conserver : la supprimer effacerait la mémoire centrale des budgets. Les anciennes dépenses locales/fournisseur sont utilisées comme planchers de migration. Les anciens workers doivent être arrêtés ou mis à jour lors du basculement ; une ancienne version ne respecte pas ce nouveau registre. Pour lancer des scripts payants depuis plusieurs machines, configurer également `BUDGET_GITHUB_TOKEN` et `GITHUB_REPOSITORY` sur ces machines : des disques locaux indépendants ne peuvent pas partager un plafond. Ne jamais placer un jeton dans le dépôt.

La limite quotidienne DataForSEO reste de 1 USD avec les exceptions datées existantes ; un plafond mensuel conservateur de 31 USD s'ajoute. Apify conserve son plafond mensuel de 35 USD et les plafonds quotidiens par rôle. Les écritures du registre nécessitent un accès GitHub disponible : s'il manque ou si le registre est illisible, aucun nouvel appel payant n'est autorisé. Ces protections ne peuvent pas empêcher un fournisseur de facturer au-delà d'un plafond qu'il ne respecterait pas ; elles bloquent les appels suivants si un dépassement est constaté.

Le workflow de qualité ajouté lance uniquement les tests simulés et la compilation, sans secrets fournisseurs. Les protections du registre ont été testées localement avec des réservations concurrentes, des conflits GitHub simulés et des pannes. Elles n'ont pas encore été éprouvées contre les comptes fournisseurs réels. La correction des budgets est préparée dans ce lot ; son activation en production nécessite le basculement ci-dessus.

## Preuves logistiques et initialisation effective du registre

La branche `budget-api` et `registre-budgets.json` ont été créés le 06/11/2026. Le registre est initialisé en mode `migration_en_cours: true` : la nouvelle version refuse toute réservation payante tant que le basculement n'est pas terminé. Les montants initiaux sont des planchers conservateurs provenant des compteurs historiques et d'une réserve quotidienne, pas une nouvelle facture ni un relevé fournisseur certifié. Ne pas les remettre à zéro. Avant de retirer le verrou, rapprocher les compteurs et vérifier que les anciens workers ont été arrêtés ou mis à jour.

Le contrôle ne se contente plus des champs booléens livraison_fr_confirmee et cout_total_confirme. Il vérifie une `preuve_livraison` datée, associée à la même URL marchande et au même prix d'article. Le collecteur PC et la relecture cloud transmettent maintenant les données de livraison de l'offre principale. Un tarif EUR exact pour la France entière permet de confirmer la destination ; un total automatique n'est calculé que si la TVA est explicitement incluse et que l'origine d'expédition déclarée est dans l'UE. Une origine absente ou hors UE, un code postal particulier, un tarif réservé aux membres, une fourchette ou plusieurs tarifs différents laissent le total à vérifier. Le port zéro est pris en compte.

Quand le total est prouvé, il remplace l'ancien port d'achat forfaitaire dans la marge et la vitrine affiche le prix livré avec un lien vers le marchand. Cela reste un relevé de la fiche fournisseur, à reconfirmer au panier avant tout futur encaissement ; aucune réservation de stock n'est présumée.

L'outil `python outils/diagnostic_preuves.py` produit un diagnostic sans réseau. L'option `--relire` effectue au maximum trois GET marchands publics, sans IA, API payante, Telegram, achat ni écriture dans les données. Le diagnostic effectué sur 334 alertes historiques et trois relectures n'a pas validé d'offre complète. Les tests synthétiques ne constituent pas une preuve qu'un fournisseur réel renseigne tous les champs ; un test de panier réel reste nécessaire avant activation commerciale.

Sources du contrat de données : https://schema.org/OfferShippingDetails et https://schema.org/valueAddedTaxIncluded.
