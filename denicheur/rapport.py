"""Page HTML du tableau (provisoire avant audit, puis remplacée par la version validée par Claude)."""
import html

NOMS = {"gemini": "Gemini", "deepseek": "DeepSeek", "nemotron": "Nemotron", "glm": "GLM", "gptoss": "gpt-oss", "qwen": "Qwen", "gemma": "Gemma", "glm45": "GLM 4.5", "nemotron_nv": "Nemotron Super"}


def _e(x):
    return html.escape(str(x if x is not None else ""))


def page(resultat, classement):
    lignes = []
    for i, c in enumerate(resultat["candidats"], 1):
        devise = "£" if c["devise"] == "GBP" else "€"
        alerte = ' <span class="tag rouge">erreur de prix ?</span>' if c["erreur_prix"] else ""
        lignes.append(
            f"<tr><td>{i}</td><td><a href='{_e(c['lien'])}' target='_blank' rel='noopener'>{_e(c['titre'])}</a>{alerte}"
            f"<div class='petit'>{_e(c['marchand'])} · {_e(c['pays'])} · {_e(c['domaine'])} · {_e(c['mode'])}</div></td>"
            f"<td>{c['prix']:.2f} {devise}</td><td>{c['prix_revente_estime']:.0f} € <span class='petit'>{_e(c['plateforme_revente'])}</span></td>"
            f"<td class='fort'>{c['marge_nette']:.0f} €</td><td>{c['rentabilite']*100:.0f} %</td>"
            f"<td>{c['demande']}/5</td><td>{c['concurrence']}/5</td>"
            f"<td>{', '.join(NOMS.get(a, a) for a in c['agents'])}</td></tr>")
    tableau = "\n".join(lignes) or "<tr><td colspan='9'>Aucune affaire au-dessus des seuils pour ce passage.</td></tr>"

    sources = "".join(f"<li>{_e(k)} : {'✅ ' + str(v['nb']) if v['ok'] else '❌ ' + _e(v['erreur'])}</li>"
                      for k, v in resultat["sources"].items())
    agents = "".join(f"<li>{_e(NOMS.get(k, k))}{' (remplaçant de ' + _e(NOMS.get(v['remplace'], v['remplace'])) + ')' if v.get('remplace') else ''} : {v['appels']} appel(s), {v['choix']} choix"
                     f"{' — ⚠️ ' + _e('; '.join(v['erreurs'][:2])) if v['erreurs'] else ''}</li>"
                     for k, v in resultat["agents"].items())
    champ = []
    for agent, s in sorted(classement.items(), key=lambda kv: -kv[1].get("global", {}).get("points", 0)):
        g = s.get("global", {})
        fi = s.get("fiabilite", {})
        champ.append(f"<tr><td>{_e(NOMS.get(agent, agent))}</td><td>{str(fi['taux']) + ' %' if fi else '–'}</td><td>{g.get('points', 0)}</td><td>{g.get('proposees', 0)}</td>"
                     f"<td>{g.get('validees', 0)}</td><td>{g.get('rejetees', 0)}</td></tr>")

    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Dénicheur – tableau du jour</title>
<style>
:root{{--fond:#f7f6f2;--texte:#1c1b19;--doux:#6b6860;--trait:#e2dfd6;--vert:#1f7a4d;--rouge:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--fond:#16150f;--texte:#ece9e0;--doux:#a19d92;--trait:#2e2c26;--vert:#5cc28d;--rouge:#ff8a80}}}}
body{{margin:0;padding:16px;font:15px/1.45 system-ui,sans-serif;background:var(--fond);color:var(--texte)}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 8px}}
.statut{{display:inline-block;padding:4px 10px;border-radius:99px;background:#f2c94c33;margin:6px 0 14px}}
.table{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:760px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid var(--trait);vertical-align:top}}
th{{font-size:13px;color:var(--doux);font-weight:600}} a{{color:inherit}}
.petit{{font-size:12px;color:var(--doux)}} .fort{{font-weight:700;color:var(--vert)}}
.tag{{font-size:11px;padding:1px 6px;border-radius:6px}} .rouge{{background:#b3261e22;color:var(--rouge)}}
ul{{padding-left:18px}}
</style></head><body>
<h1>Dénicheur – tableau du {_e(resultat['date_affichee'])}</h1>
<div class="statut">{_e(resultat.get('statut', 'Provisoire : en attente de l’audit de Claude'))}</div>
<div class="table"><table><thead><tr><th>#</th><th>Produit</th><th>Prix promo</th><th>Revente estimée</th><th>Marge nette</th>
<th>Rentabilité</th><th>Demande</th><th>Concurrence</th><th>Trouvé par</th></tr></thead><tbody>
{tableau}</tbody></table></div>
<h2>Championnat des IA</h2>
<div class="table"><table><thead><tr><th>IA</th><th>Fiabilité</th><th>Points</th><th>Proposées</th><th>Validées</th><th>Rejetées</th></tr></thead>
<tbody>{''.join(champ) or "<tr><td colspan='6'>Pas encore de résultats.</td></tr>"}</tbody></table></div>
<h2>Fonctionnement du passage « {_e(resultat['passage'])} »</h2>
<p class="petit">{resultat['nb_annonces']} bons plans lus · {resultat['nb_prefiltres']} après filtre · {resultat['nb_tries']} après tri</p>
<ul>{sources}</ul><ul>{agents}</ul>
</body></html>"""
