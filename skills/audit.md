# Méthode d'audit du Dénicheur (appliquée chaque matin par Claude)

But : David ne doit rien avoir à vérifier. Chaque affaire du dernier passage « europe » est
**validée** ou **rejetée** avec un motif court, en français simple.

## Règles de vérification (pour chaque affaire de `data/dernier_passage.json` → `candidats`)
1. **Prix neuf le plus bas en France aujourd'hui**, dans cet ordre :
   a. le champ `idealo` de l'affaire (ou `prix_plancher.ou == "idealo"`) : relevé automatiquement par le robot
      Apify pendant le passage pour les meilleures affaires. **Il compte comme le prix idealo** : contrôler
      seulement que `idealo.titre` est bien le même produit (même modèle, même capacité).
   b. sinon **idealo.fr** dans le navigateur intégré, si l'ordinateur de David est joignable
      (recherche `idealo.fr/prechcat.html?q=<nom_produit>`, à rythme humain, jamais en masse) ;
   c. sinon recherche web (comparateurs, sites marchands français) : le dire dans le commentaire.
   Les prix eBay sont des prix DEMANDÉS : ils ne remplacent jamais idealo.
   Depuis le 04/11 : le champ `keepa` (fiche Amazon.fr trouvée par le robot : `prix_neuf`, `moyenne_90j`, `nb_vendeurs_neuf`,
   `ventes_estimees_30j`, `ean`, `asin`) compte AUSSI comme prix neuf de référence (`prix_plancher.ou == "keepa/amazon.fr"`),
   à condition que `keepa.titre` soit le même produit. Contrôler l'écart entre `keepa.prix_neuf` et `keepa.moyenne_90j` :
   un prix Amazon anormalement haut (vendeur tiers) ne doit pas servir de référence ; prendre alors la moyenne 90 j.
   - Si le produit est déjà moins cher ou au même prix ailleurs en neuf → **rejet**.
2. **Prix de revente réaliste** sur la plateforme visée :
   - Vinted / Leboncoin / eBay : fourchette des annonces comparables (neuf ou très bon état).
   - Le prix retenu ne dépasse JAMAIS 85 % du neuf le moins cher, ni le haut de la fourchette d'occasion.
   - Si `verification` (Gemini + Google) existe déjà dans l'affaire, s'en servir et la contrôler.
3. **Marge nette** = prix de revente retenu − `cout_achat` (déjà frais de port et taxes compris),
   moins la commission de la plateforme (voir `config/regles.json`).
   - Deux niveaux (la marge est calculée sur le MEILLEUR canal de vente, voir `canaux`) :
     * « valide » (sûr) : marge ≥ 8 € ET ≥ 30 % du coût ;
     * « bon » (à tenter en petite quantité) : marge ≥ 20 € ET ≥ 15 % du coût.
     Le prix neuf le plus bas d'idealo (robot ou navigateur) est OBLIGATOIRE avant tout « valide » ou « bon ».
     Sans idealo mais avec un prix neuf français sûr (page marchand lue) : « bon » au maximum, jamais « valide ».
4. **Rejets automatiques** : achat impossible depuis la France (magasin physique étranger, carte de
   fidélité obligatoire), batterie seule, alimentaire, produit sous licence douteuse, demande en chute
   (après un événement), taille unique pour un vêtement, « erreur de prix » probable (le dire).
5. **Mode et canal de vente** (pour chaque affaire validée) :
   - `mode` : `stock` (acheter, recevoir, revendre), `dropshipping` (vendre d'abord, le marchand livre
     directement le client) ou `les_deux`. Dropshipping seulement si : l'offre dure (pas une vente flash),
     le marchand livre le pays du client avec suivi, et le canal l'autorise (jamais Leboncoin ni Vinted :
     il faut avoir l'objet en main ; eBay : seulement depuis un grossiste, pas depuis un magasin).
   - `ou_vendre` : canal + pays, ex. « Leboncoin (France) », « Vinted (France, Italie, Espagne) »,
     « eBay Allemagne ». Se servir de `ebay.neuf_par_pays` / `meilleur_pays` pour choisir le pays.
5 bis. **Carte trois feux** (champ `feu` calculé par le robot : vert / orange / rouge) : l'audit confirme ou rétrograde.
   - Concurrence (`vendeurs_amazon`, `concurrence_amazon`) : ≥ 10 vendeurs → rouge sauf si on est ≥ 15 % sous le moins cher ;
     5 à 9 → orange ; ≤ 4 → peut être vert. Compter aussi les gros sites (Fnac, Cdiscount, Boulanger) au même prix.
   - Occasion (`occasion.bas` / `occasion.haut` / `position_neuf`) : si notre coût d'achat dépasse le HAUT de l'occasion → rouge.
     Si notre prix est sous le BAS de l'occasion → signaler « or » dans le commentaire.
   - `bingo` (très recherché, peu vendu) : le dire dans le commentaire, c'est prioritaire pour David.
   - Vert = marge ≥ 20 € ET prix neuf prouvé ET concurrence faible ; orange = marge 8-20 € ou preuve partielle ; sinon rouge.
   Le verdict écrit : `valide` (vert), `bon` (orange), `rejete` (rouge).
6. En cas de doute sans preuve → **rejet** (motif : « prix de revente non confirmé »). Mieux vaut
   rater une affaire que d'en valider une fausse.

## Fichier d'audit à écrire : `data/audits/<horodatage du passage>.json`
```json
{"horodatage": "...", "date": "JJ/MM/AAAA", "auditeur": "Claude",
 "resume": "N validées sur M. <2 phrases sur les meilleures et les motifs de rejet>",
 "verdicts": [{"id": "...", "verdict": "valide|bon|rejete", "commentaire": "...",
               "prix_revente_verifie": 0, "plateforme_verifiee": "leboncoin", "marge_nette_verifiee": 0,
               "mode": "stock|dropshipping|les_deux", "ou_vendre": "Leboncoin (France)"}],
 "valides": ["id", "..."],
 "rejetes": [{"id": "...", "motif": "..."}]}
```
`prix_revente_verifie`, `plateforme_verifiee` et `marge_nette_verifiee` seulement quand le prix a été vérifié.

## Après l'audit
`python -m denicheur.apres_audit` : recalcule le championnat et reconstruit `saas/index.html`.
Puis `python saas/rapport_david.py` : la page à onglets de David (`data/rapport_david.html`). Lire `skills/rapport.md` :
jamais de rapport vide ni d'excuse technique ; s'il n'y a aucune carte verte ni orange, ne pas envoyer, réparer et relancer.

## Message à David (court, en français)
- Nombre d'affaires validées, marge totale, la meilleure affaire (prix d'achat → revente, lien).
- Ce qui n'a pas marché (source bloquée, IA absente) en une ligne si besoin.
