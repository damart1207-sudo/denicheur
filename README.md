# Dénicheur

Agent d'arbitrage de prix de David. Il tourne tout seul sur les serveurs de GitHub
(ton PC peut rester éteint) et ne coûte rien : GitHub gratuit + 5 IA gratuites.

## Chaque jour
| Heure de Paris (hiver) | Heure de Pékin | Ce qui se passe |
|---|---|---|
| 17 h 30 | 0 h 30 | Passage « asie » : les nouvelles promos du jour chinois |
| 3 h | 10 h | Passage « europe » : collecte, tri, analyse par les 5 IA, calcul des marges |
| ~5 h 15 | 12 h 15 | Claude vérifie, rédige l'audit et t'envoie le tableau validé |

Les horaires sont réglés sur l'heure de Pékin : ils suivent la Chine toute l'année.
À l'heure d'été en France, tout arrive une heure plus tard à Paris.

## L'équipe (config/equipe.json)
| Rôle | IA | Marque | Secret GitHub |
|---|---|---|---|
| Trieur | GLM-4.7-Flash | Z.ai | `ZAI_API_KEY` |
| Analyste | Gemini 3.8 Flash | Google | `GEMINI_API_KEY` |
| Analyste | DeepSeek V4.1 Flash | DeepSeek (via NVIDIA) | `NVIDIA_API_KEY` |
| Analyste | Nemotron 3 Ultra | NVIDIA (via OpenRouter) | `OPENROUTER_API_KEY` |
| Analyste | gpt-oss-120b | OpenAI (via Groq) | `GROQ_API_KEY` |

Les 4 analystes reçoivent exactement les mêmes bons plans : c'est la base du championnat.

## Où trouver les résultats
- `data/rapport.html` : le tableau du dernier passage
- `data/dernier_passage.json` : les données complètes (lues par Claude pour l'audit)
- `data/classement.json` : le championnat des IA
- `data/audits/` : les audits de Claude (validés / rejetés), qui donnent les points

## Garde-fous
- 25 minutes maximum par passage, plafond d'appels par IA et par passage.
- Une IA qui réclame un paiement (erreur 402) est coupée immédiatement.
- Aucune carte bancaire enregistrée nulle part : rien ne peut être facturé.

## Réglages sans toucher au code
- `config/sources.json` : les flux de bons plans
- `config/regles.json` : frais des plateformes, seuils de marge
- `skills/methode.md` : la méthode donnée aux IA

## Test gratuit
`python -m denicheur --test` : aucune connexion, aucune IA appelée.
