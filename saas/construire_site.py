"""Site public du comparateur (GitHub Pages, dossier docs/) : uniquement les affaires VÉRIFIÉES par Claude,
comparées au prix neuf le plus bas en France. Page statique (lisible par Google et par les réseaux d'affiliation).

python saas/construire_site.py
"""
import glob
import html
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(RACINE, "docs")
NOM_SITE = "Dénicheur"
TAUX = {"GBP": 1.15, "EUR": 1.0}
PAYS = {"FR": "France", "DE": "Allemagne", "ES": "Espagne", "IT": "Italie", "UK": "Royaume-Uni", "PL": "Pologne",
        "AT": "Autriche", "NL": "Pays-Bas"}


def lire(c, d=None):
    try:
        return json.load(open(os.path.join(RACINE, c), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return d


def e(t):
    return html.escape(str(t if t is not None else ""))


def euro(v):
    return f"{v:,.2f} €".replace(",", " ").replace(".", ",").replace(",00 €", " €")


def ref_depuis_texte(t):
    m = re.search(r"idealo[^0-9]{0,40}?(\d[\d\s]*,\d{2}|\d[\d\s]*)\s?€", t or "")
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def affaires():
    candidats = {}
    for f in glob.glob(os.path.join(RACINE, "data/passages/*.json")):
        p = lire(os.path.relpath(f, RACINE), {}) or {}
        for c in p.get("candidats", []):
            candidats[c["id"]] = {**c, "_h": p.get("horodatage")}
    out = []
    for f in glob.glob(os.path.join(RACINE, "data/audits/*.json")):
        a = lire(os.path.relpath(f, RACINE), {}) or {}
        for v in a.get("verdicts", []):
            if v.get("verdict") not in ("valide", "bon") or v["id"] not in candidats:
                continue
            c = candidats[v["id"]]
            ref = ((c.get("prix_plancher") or {}).get("prix_min") or (c.get("verification") or {}).get("prix_neuf_min")
                   or ref_depuis_texte(v.get("commentaire")))
            out.append({"nom": c.get("nom_produit") or c["titre"], "titre": c["titre"], "prix": c["prix"] * TAUX.get(c.get("devise"), 1),
                        "marchand": c.get("marchand"), "pays": c.get("pays"), "lien": c.get("lien"), "ref": ref,
                        "verifie": a.get("horodatage", "")[:10], "commentaire": v.get("commentaire")})
    for x in lire("data/alertes.json", []) or []:
        if x.get("statut") not in ("valide", "bon"):
            continue
        vd = x.get("verdict") or {}
        ref = vd.get("prix_neuf_min_idealo") or (x.get("idealo") or {}).get("prix_min") or (x.get("prix_plancher") or {}).get("prix_min")
        out.append({"nom": x.get("nom_produit") or x["titre"], "titre": x["titre"], "prix": x["prix"] * TAUX.get(x.get("devise"), 1),
                    "marchand": x.get("marchand"), "pays": x.get("pays"), "lien": x.get("lien"), "ref": ref,
                    "verifie": (x.get("verifie_le") or x.get("trouve_le") or "")[:10], "commentaire": vd.get("commentaire")})
    # pas de publication si la livraison en France n'est pas confirmée
    out = [o for o in out if o["ref"] and o["ref"] > o["prix"] and "CONDITION" not in (o.get("commentaire") or "")]
    for o in out:
        o["economie"] = o["ref"] - o["prix"]
        o["pct"] = round(100 * o["economie"] / o["ref"])
    out.sort(key=lambda o: (o["verifie"], o["pct"]), reverse=True)
    return out


def date_fr(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def carte(o, aujourd_hui):
    age = (aujourd_hui - datetime.fromisoformat(o["verifie"]).date()).days if o["verifie"] else 99
    etat = "Vérifiée aujourd'hui" if age == 0 else (f"Vérifiée le {date_fr(o['verifie'])}" + (" · l'offre a peut-être expiré" if age > 2 else ""))
    origine = f"chez {e(o['marchand'] or 'le marchand')}" + (f", expédié depuis {e(PAYS.get(o['pays'], o['pays']))}" if o.get("pays") and o["pays"] != "FR" else "")
    lien = f'<a class="voir" href="{e(o["lien"])}" rel="nofollow sponsored noopener" target="_blank">Voir l\'offre</a>' if o.get("lien") else ""
    return f"""<li class="etiquette{' ancienne' if age > 2 else ''}">
  <div class="produit"><h3>{e(o['nom'])}</h3><p class="origine">{origine}</p><p class="etat">{etat}</p></div>
  <div class="prix">
    <p class="ici"><span class="montant">{euro(o['prix'])}</span></p>
    <p class="ailleurs">Le moins cher ailleurs en France : <s>{euro(o['ref'])}</s></p>
    <p class="gain">{euro(o['economie'])} de moins, soit −{o['pct']} %</p>
    {lien}
  </div>
</li>"""


def construire():
    aujourd_hui = datetime.now(ZoneInfo("Europe/Paris")).date()
    liste = affaires()
    dm = lire("data/demande.json", {}) or {}
    tendances = [x for x in dm.get("liste", []) if x.get("pays") == "FR"][:12]
    une = liste[0] if liste else None
    modele = open(os.path.join(RACINE, "saas/site_modele.html"), encoding="utf-8").read()
    rempl = {
        "{{NOM}}": e(NOM_SITE),
        "{{MAJ}}": datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y à %Hh%M"),
        "{{NB}}": str(len(liste)),
        "{{UNE}}": carte(une, aujourd_hui).replace('<li class="etiquette', '<div class="etiquette grande').replace("</li>", "</div>") if une else "<p>Aucune affaire vérifiée pour le moment. Revenez dans une heure.</p>",
        "{{LISTE}}": "\n".join(carte(o, aujourd_hui) for o in liste[1:]) or '<li class="vide">Les prochaines affaires vérifiées apparaîtront ici.</li>',
        "{{TENDANCES}}": "\n".join(f'<li><span class="q">{e(t["recherche"])}</span><span class="h">{"nouveau" if t.get("nouveau") or (t.get("hausse_pct") or 0) > 1000 else "+" + str(t.get("hausse_pct")) + " %"}</span></li>' for t in tendances) or "<li>Données en cours de collecte.</li>",
    }
    for k, v in rempl.items():
        modele = modele.replace(k, v)
    os.makedirs(DOCS, exist_ok=True)
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(modele)
    ml = open(os.path.join(RACINE, "saas/site_mentions.html"), encoding="utf-8").read().replace("{{NOM}}", e(NOM_SITE))
    open(os.path.join(DOCS, "mentions-legales.html"), "w", encoding="utf-8").write(ml)
    open(os.path.join(DOCS, ".nojekyll"), "w").write("")
    print(f"docs/index.html : {len(liste)} affaires vérifiées, {len(tendances)} tendances")


if __name__ == "__main__":
    construire()
