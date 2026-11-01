# Méthode d'audit du Dénicheur (appliquée chaque matin par Claude)

But : David ne doit rien avoir à vérifier. Chaque affaire du dernier passage « europe » est
**validée** ou **rejetée** avec un motif court, en français simple.

## Règles de vérification (pour chaque affaire de `data/dernier_passage.json` → `candidats`)
1. **Prix neuf le plus bas en France aujourd'hui** : vérifier sur **idealo.fr** dans le navigateur intégré
   (recherche `idealo.fr/prechcat.html?q=<nom_produit>`, à rythme humain, jamais en masse), puis recherche web.
   Les prix eBay sont des prix DEMANDÉS : ils ne remplacent jamais idealo.
   - Si le produit est déjà moins cher ou au même prix ailleurs en neuf → **rejet**.
2. **Prix de revente réaliste** sur la plateforme visée :
   - Vinted / Leboncoin / eBay : fourchette des annonces comparables (neuf ou très bon état).
   - Le prix retenu ne dépasse JAMAIS 85 % du neuf le moins cher, ni le haut de la fourchette d'occasion.
   - Si `verification` (Gemini + Google) existe déjà dans l'affaire, s'en servir et la contrôler.
3. **Marge nette** = prix de revente retenu − `cout_achat` (déjà frais de port et taxes compris),
   moins la commission de la plateforme (voir `config/regles.json`).
   - Valider seulement si marge ≥ 8 € ET marge ≥ 30 % du coût.
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
6. En cas de doute sans preuve → **rejet** (motif : « prix de revente non confirmé »). Mieux vaut
   rater une affaire que d'en valider une fausse.

## Fichier d'audit à écrire : `data/audits/<horodatage du passage>.json`
```json
{"horodatage": "...", "date": "JJ/MM/AAAA", "auditeur": "Claude",
 "resume": "N validées sur M. <2 phrases sur les meilleures et les motifs de rejet>",
 "verdicts": [{"id": "...", "verdict": "valide|rejete", "commentaire": "...",
               "prix_revente_verifie": 0, "plateforme_verifiee": "leboncoin", "marge_nette_verifiee": 0,
               "mode": "stock|dropshipping|les_deux", "ou_vendre": "Leboncoin (France)"}],
 "valides": ["id", "..."],
 "rejetes": [{"id": "...", "motif": "..."}]}
```
`prix_revente_verifie`, `plateforme_verifiee` et `marge_nette_verifiee` seulement quand le prix a été vérifié.

## Après l'audit
`python -m denicheur.apres_audit` : recalcule le championnat et reconstruit `saas/index.html`.

## Message à David (court, en français)
- Nombre d'affaires validées, marge totale, la meilleure affaire (prix d'achat → revente, lien).
- Ce qui n'a pas marché (source bloquée, IA absente) en une ligne si besoin.
