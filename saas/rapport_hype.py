"""Rapport HYPE & RADAR lisible (HTML) à partir de data/hype_etranger.json, data/radar_amazon.json, data/bingo.json.
-> data/rapport_hype.html   (reconstruit à chaque tour de veille, à ouvrir dans le navigateur)
python saas/rapport_hype.py"""
import html
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(rel, defaut):
    try:
        return json.load(open(os.path.join(RACINE, rel), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaut


def e(t):
    return html.escape(str(t if t is not None else "—"))


def euro(v):
    return f"{v:.2f} €".replace(".", ",") if isinstance(v, (int, float)) else "—"


def heure(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m à %H h %M")
    except (TypeError, ValueError):
        return "—"


DRAPEAU = {"US": "🇺🇸 USA", "JP": "🇯🇵 Japon", "FR": "🇫🇷"}
STYLE = """body{font-family:system-ui,Segoe UI,Arial;max-width:1100px;margin:20px auto;padding:0 14px;color:#222;background:#fafafa}
h1{font-size:1.5em}h2{margin-top:34px;border-bottom:2px solid #ddd;padding-bottom:4px}
table{border-collapse:collapse;width:100%;font-size:.93em;background:#fff}th,td{border:1px solid #e3e3e3;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f0f0f0}tr:nth-child(even){background:#fbfbfb}.ok{color:#1a7f37;font-weight:600}.mal{color:#b35900;font-weight:600}
.pct{font-weight:700;color:#1a7f37}.note{color:#666;font-size:.9em}a{color:#0b57d0;text-decoration:none}a:hover{text-decoration:underline}
.encadre{background:#fff7e0;border:1px solid #f0d58c;padding:10px 14px;border-radius:8px;margin:10px 0}"""


def construire():
    hype, radar, bingo = lire("data/hype_etranger.json", {}), lire("data/radar_amazon.json", {}), lire("data/bingo.json", {})
    etat = lire("data/etat/moisson.json", {})
    nb_base = len(lire("data/base/keepa_index.json", {}))
    maintenant = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y à %H h %M")
    h = [f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Dénicheur — hype, radar, bingo</title><style>{STYLE}</style></head><body>",
         f"<h1>Rapport hype étrangère, radar Amazon et bingo</h1>",
         f"<p class='note'>Construit le {maintenant}. Base Keepa : <b>{nb_base}</b> fiches produits. "
         f"Jetons Keepa dépensés aujourd'hui : {etat.get('jetons_jour', 0)} (tours : {etat.get('tours', 0)}). Aucun coût en plus de l'abonnement.</p>",
         "<div class='encadre'>Comment lire : <b>absent</b> = pas d'offre neuve sur Amazon.fr aujourd'hui ; <b>mal vendu</b> = en vente mais classement faible "
         "(rang &gt; 20 000). « Ventes 30 j » = chutes de classement Amazon là-bas (≈ 1 par vente). Ce sont des pistes pour Amigo, pas des affaires vérifiées : "
         "le tribunal et l'audit décident.</div>"]

    # ---- LES PLUS RECHERCHÉS (Amigo) et ce que les dénicheurs ont trouvé dessus
    dem = lire("data/demande.json", {})
    recents = lire("data/etat/annonces_recentes.json", [])
    alertes = lire("data/alertes.json", [])
    chasse = dem.get("chasse", []) or []

    def mots(t):
        import re, unicodedata
        t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
        return set(m for m in re.findall(r"[a-z0-9]+", t) if len(m) > 1)

    top = [x for x in dem.get("liste", []) if x.get("pays") == "FR"][:25]
    h.append(f"<h2>0. Les plus recherchés en France (idealo, mise à jour {heure(dem.get('maj'))}) et ce qu'on a trouvé</h2>")
    h.append("<p class='note'>« Recherches en hausse » sur idealo.fr. Pour chacune : les promos vues par Idéfix dont le titre contient tous les mots "
             "de la recherche, les alertes de veille, et le résultat de la chasse ciblée de Chasseur (idealo + Leboncoin + Vinted, 1 fois par jour sur les 3 premières).</p>")
    if top:
        h.append("<table><tr><th>#</th><th>Recherche</th><th>Popularité</th><th>Hausse</th><th>Promos vues (titre complet)</th><th>Alertes</th><th>Chasse ciblée</th></tr>")
        for i, x in enumerate(top, 1):
            q = mots(x.get("recherche"))
            vues = [r for r in recents if q and q <= mots(r.get("titre"))]
            al = [a for a in alertes if q and q <= mots(a.get("titre"))]
            ch = [c for c in chasse if (c.get("recherche") or "").lower() == (x.get("recherche") or "").lower()]
            cell = "<br>".join(f"<a href='{e(r.get('lien'))}' target='_blank'>{euro(r.get('prix'))} — {e((r.get('titre') or '')[:60])}</a>" for r in vues[:3]) or "—"
            cell_a = "<br>".join(f"{e(a.get('statut'))} : {euro(a.get('prix'))} {e((a.get('titre') or '')[:50])}" for a in al[:3]) or "—"
            cell_c = "<br>".join(f"{e(c.get('canal'))} {euro(c.get('annonce_min'))}" for c in ch[:3]) or ("rien trouvé" if i <= 3 and chasse is not None else "—")
            h.append(f"<tr><td>{i}</td><td><b>{e(x.get('recherche'))}</b></td><td>{e(x.get('popularite'))}</td><td>+{e(x.get('hausse_pct'))} %</td>"
                     f"<td>{cell}</td><td>{cell_a}</td><td>{cell_c}</td></tr>")
        h.append("</table>")
    else:
        h.append("<p>Liste idealo pas encore chargée.</p>")

    # ---- HYPE
    prods = hype.get("produits", [])
    h.append(f"<h2>1. Hype étrangère — {len(prods)} produits (mise à jour {heure(hype.get('maj'))})</h2>")
    if not prods:
        h.append("<p>Rien encore : la récolte tourne un tour sur trois.</p>")
    for pays in ("US", "JP"):
        sel = [x for x in prods if x.get("pays") == pays]
        if not sel:
            continue
        sel.sort(key=lambda x: -(x.get("ventes_30j_labas") or 0))
        h.append(f"<h3>{DRAPEAU.get(pays, pays)} — {len(sel)} produits</h3><table><tr><th>#</th><th>Produit</th><th>Catégorie</th>"
                 f"<th>Rang là-bas</th><th>Ventes 30 j là-bas</th><th>Prix là-bas</th><th>En France</th><th>Prix FR</th><th>Rang FR</th><th>Vu</th></tr>")
        for i, x in enumerate(sel[:80], 1):
            cl = "ok" if x.get("en_france") == "absent" else "mal"
            h.append(f"<tr><td>{i}</td><td><a href='{e(x.get('lien_fr'))}' target='_blank'>{e((x.get('titre') or '')[:110])}</a>"
                     f"<div class='note'>{e(x.get('marque'))} · {e(x.get('asin'))}</div></td><td>{e(x.get('categorie'))}</td>"
                     f"<td>{e(x.get('rang_labas'))}</td><td><b>{e(x.get('ventes_30j_labas'))}</b></td><td>{euro(x.get('prix_labas'))}</td>"
                     f"<td class='{cl}'>{e(x.get('en_france'))}</td><td>{euro(x.get('prix_fr'))}</td><td>{e(x.get('rang_fr'))}</td><td>{e(x.get('vu'))}</td></tr>")
        h.append("</table>")

    # ---- RADAR
    aff = radar.get("affaires", [])
    h.append(f"<h2>2. Radar Amazon.fr — {len(aff)} baisses de prix (mise à jour {heure(radar.get('maj'))})</h2>")
    if aff:
        h.append("<table><tr><th>#</th><th>Produit</th><th>Type</th><th>Prix du jour</th><th>Moyenne 90 j</th><th>Baisse</th><th>Rang ventes</th><th>Vu</th></tr>")
        for i, a in enumerate(aff[:120], 1):
            typ = "neuf" if a.get("type") == "neuf" else f"seconde main (état {a.get('etat_seconde_main')})"
            h.append(f"<tr><td>{i}</td><td><a href='{e(a.get('lien'))}' target='_blank'>{e((a.get('titre') or '')[:110])}</a></td><td>{e(typ)}</td>"
                     f"<td><b>{euro(a.get('prix'))}</b></td><td>{euro(a.get('moyenne_90j'))}</td><td class='pct'>-{e(a.get('baisse_pct'))} %</td>"
                     f"<td>{e(a.get('rang'))}</td><td>{e((a.get('vu') or '')[5:16].replace('T', ' '))}</td></tr>")
        h.append("</table>")

    # ---- BINGO
    bingos = bingo.get("bingos", [])
    h.append(f"<h2>3. Bingo — très recherché, peu vendu ({len(bingos)} ; mise à jour {heure(bingo.get('maj'))})</h2>")
    if not bingo:
        h.append("<p>Pas encore calculé : le bingo tourne une fois par jour, au passage de la nuit.</p>")
    else:
        h.append(f"<p class='note'>{bingo.get('nb_candidats')} candidats, {bingo.get('nb_avec_volume')} avec un volume Google connu.</p>")
        h.append("<table><tr><th>#</th><th>Mot-clé (ce que les gens tapent)</th><th>Recherches / mois (FR)</th><th>Vendeurs Amazon</th><th>Annonces eBay</th><th>Prix</th><th>Origine</th><th>Score</th></tr>")
        for i, x in enumerate(bingos[:60], 1):
            h.append(f"<tr><td>{i}</td><td><b>{e(x.get('mot_cle'))}</b><div class='note'>{e((x.get('titre') or '')[:90])}</div></td><td><b>{e(x.get('recherches_mois'))}</b></td>"
                     f"<td>{e(x.get('vendeurs'))}</td><td>{e(x.get('annonces_ebay', '—'))}</td><td>{euro(x.get('prix'))}</td><td>{e(x.get('origine'))}</td><td>{e(x.get('score'))}</td></tr>")
        h.append("</table>")
        vagues = bingo.get("vagues", [])
        if vagues:
            h.append("<h3>Vagues à venir en France (monte à l'étranger, pas encore ici)</h3><ul>")
            for v in vagues:
                h.append(f"<li><b>{e(v.get('mot_cle'))}</b> — monte dans {e(', '.join(v.get('monte_dans') or []))} · <a href='https://www.amazon.fr/dp/{e(v.get('asin'))}' target='_blank'>Amazon.fr</a></li>")
            h.append("</ul>")
    h.append("</body></html>")
    chemin = os.path.join(RACINE, "data/rapport_hype.html")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("\n".join(h))
    print(f"data/rapport_hype.html : {len(prods)} hype, {len(aff)} radar, {len(bingos)} bingo")


if __name__ == "__main__":
    construire()
