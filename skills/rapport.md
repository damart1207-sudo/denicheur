# Consigne de David pour les rapports du Dénicheur (04/11/2026) — à appliquer par Claude, toujours

1. **Jamais de rapport vide ni d'excuse technique.** Un rapport ne part que s'il contient des bons plans
   chiffrés (prix d'achat, prix de revente vérifié, marge, canal), signés par le dénicheur qui les a trouvés
   (Idéfix, Amigo, Chasseur, Radar Keepa). Quotas, pages bloquées, IA saturées : ça se règle, ça ne s'écrit pas.
2. **Boucle réparation → relance → vérification.** Si un cycle sort sans bon plan ou avec un outil cassé :
   réparer aussitôt (réglage, paramètre, remplaçant, autre source), relancer un vrai passage, lire le résultat,
   recommencer. Toute la journée s'il le faut. Rien n'est envoyé à David tant que le process n'est pas
   opérationnel à 100 %. Quand le rapport est bon : l'envoyer en disant « tout est réparé et opérationnel ».
3. **Outils manquants.** Si un outil manque vraiment pour atteindre l'objectif, le dire à David avec le coût
   exact et la voie gratuite d'abord ; sinon, faire avec les outils déjà payés (Keepa, Apify, DataForSEO,
   Gemini, eBay) et les IA gratuites, en utilisant TOUS les jetons Keepa chaque jour.
4. **Rien n'est annoncé « en place » avant d'avoir tourné en réel avec un chiffre.** Tester d'abord, affirmer ensuite.
5. **Format** : page HTML à onglets avec tri et filtres (`saas/rapport_david.py` → `data/rapport_david.html`).
   Horaires voulus : 5 h, 13 h, 18 h (Paris). Pas d'exemples inventés : les tests se font sur les produits
   réels sortis par Amigo.
6. **Chaîne de décision** : gros volume de recherche → produit trouvé au prix le plus bas → concurrence
   (≥ 10 vendeurs dont un gros site au même prix : on passe ; 5-9 : seulement si ≥ 15 % moins cher ;
   ≤ 4 et moins cher : BINGO) → fourchette d'occasion (plus bas / plus haut réellement vendus) et position
   de notre neuf dedans. En parallèle, Idéfix alerte sur tout écart de prix (ex. 100 € idealo, trouvé 50 €),
   sans attendre le volume.
