"""BILAN d'une affaire « écart vendeurs » (demande de David, 17/11/2026), ajouté à la fin de chaque alerte Telegram :
 1. l'avis d'un EXPERT e-commerce : je vends ce produit ou non ; si oui, où et à quel prix ;
 2. l'avis d'un ACHETEUR placé devant l'annonce à ce prix : j'achète ou non, et pourquoi.

Une IA rédige les deux avis à partir des SEULS chiffres relevés (prix, ventes, volume de recherche, comparateurs,
annonces Leboncoin / Vinted / eBay et leur ancienneté). Garde-fous : aucun chiffre accepté de l'IA en dehors du prix de
vente conseillé, lui-même borné entre notre achat et le 2e vendeur ; les deux marges à ce prix sont recalculées ici
(denicheur/rentabilite.py). Un appel par alerte : Gemini (dans son plafond existant), sinon les IA gratuites de l'équipe.
Sans réponse valable, l'alerte part sans bilan : jamais un avis inventé.
"""
import json
import os
import re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANAUX = {"leboncoin": "Leboncoin", "vinted": "Vinted", "ebay": "eBay", "amazon": "Amazon"}
ORDRE_IA = ("gemini", "deepseek", "glm", "gptoss", "nemotron_nv")
SYSTEME = """Tu rends un bilan sur un produit acheté neuf pour être revendu neuf par un particulier ou une micro-entreprise en France.
Tu tiens deux rôles, l'un après l'autre, et tu réponds UNIQUEMENT par un objet JSON :
{"expert": {"vendre": "OUI" ou "NON", "ou": "leboncoin" | "vinted" | "ebay" | "amazon" | null, "prix": nombre ou null, "raisons": "..."},
 "acheteur": {"acheter": "OUI" ou "NON", "raisons": "..."}}

Rôle 1, EXPERT e-commerce : décide si tu revends ce produit. Si OUI : le site où il partira le mieux et UN prix de vente en euros,
strictement entre le prix d'achat et le prix du 2e vendeur. Dis NON si la demande est faible (peu de ventes, peu de recherches),
si le produit est déjà affiché à ton prix d'achat dans les comparateurs, si des annonces moins chères existent déjà,
ou si des annonces traînent depuis des semaines sans se vendre.
Rôle 2, ACHETEUR : tu es devant l'annonce de ce produit au prix conseillé par l'expert (ou au prix de revente indiqué si l'expert
dit NON), sur le site choisi. Tu compares avec ce que tu trouves en deux minutes : comparateurs, Amazon, autres annonces.
Dis si tu achètes, OUI ou NON, et pourquoi.

La demande se juge d'abord sur les ventes Amazon (50 achats ou plus par mois = forte, moins de 15 ventes sur 30 jours = faible),
ensuite sur les recherches Google ; un volume « trop peu pour être mesuré » ou « inconnu » ne prouve pas à lui seul une demande faible.
Règles : n'utilise QUE les chiffres de la fiche, n'invente aucun prix ni aucune donnée ; une information absente de la fiche est
inconnue, dis-le au lieu de la deviner. « raisons » : 2 phrases au plus, en français simple, en tutoyant, avec les chiffres qui comptent."""


def _eur(v):
    return f"{v:.2f}".replace(".", ",").replace(",00", "") + " €" if isinstance(v, (int, float)) else "inconnu"


def _site(nom, r):
    if r is None:
        return f"- {nom} : non consulté (inconnu)"
    if not r.get("nb"):
        return f"- {nom} : aucune annonce"
    t = f"- {nom} : {r['nb']} annonce(s), de {_eur(r['min'])} à {_eur(r['max'])}"
    if r.get("age_min") is not None:
        t += (f" ; la moins chère est en ligne depuis {r['age_min']} jours ; {r['recentes']} publiée(s) depuis 7 jours, "
              f"{r['anciennes']} en ligne depuis plus de 21 jours, la plus ancienne {r['age_ancien']} jours")
    else:
        t += " ; dates de publication inconnues"
    return t


def fiche_texte(f):
    """Tous les chiffres relevés, en clair, pour l'IA (et rien d'autre)."""
    m, mk = f.get("marges") or {}, f.get("marche") or {}
    t = [f"Produit : {f.get('titre')}",
         f"Prix d'achat (vendeur le moins cher sur Amazon, neuf, port compris) : {_eur(f.get('premier'))}",
         f"Prix du 2e vendeur Amazon : {_eur(f.get('second'))} ; moyenne Amazon sur 90 jours : {_eur(f.get('moyenne_90j'))} ; {f.get('nb_offres_neuves')} vendeurs en neuf",
         "Ventes Amazon : " + (f"{f['achetes_mois_amazon']}+ achetés le mois dernier ; " if f.get("achetes_mois_amazon") else "")
         + (f"environ {f['ventes_estimees_30j']} ventes sur 30 jours ; " if f.get("ventes_estimees_30j") is not None else "ventes inconnues ; ")
         + (f"classement {f['rang']}" if f.get("rang") else "classement inconnu"),
         "Recherches Google par mois en France : " + (f"{f['volume']} pour « {f.get('volume_mot') or f.get('mot_cle')} »"
                                                      if f.get("volume") else "trop peu pour être mesuré" if f.get("volume") == 0 else "inconnu")]
    c = mk.get("comparateur_min")
    if c and c["prix"] >= 0.7 * f["premier"]:
        t.append(f"Comparateurs de prix : le moins cher du neuf à {_eur(c['prix'])} sur {c['ou']}" + (f" ({c['nb_offres']} offres)" if c.get("nb_offres") else ""))
    elif c:
        t.append(f"Comparateurs de prix : {_eur(c['prix'])} sur {c['ou']}, mais sans doute un autre modèle (non fiable)")
    elif mk.get("comparateurs_consultes"):
        t.append("Comparateurs de prix : produit introuvable sur " + " et ".join(mk["comparateurs_consultes"]))
    else:
        t.append("Comparateurs de prix : non consultés (inconnu)")
    t.append("Annonces déjà en ligne (tous états confondus sauf mention) :")
    t.append(_site("Leboncoin", mk.get("leboncoin")))
    v = mk.get("vinted")
    t.append(_site("Vinted", v) + (f" ; dont {v['neuf']['nb']} en neuf dès {_eur(v['neuf']['min'])}" if v and v.get("nb") and v["neuf"].get("nb") else ""))
    e = mk.get("ebay")
    t.append(_site("eBay neuf", e.get("neuf")) if e else _site("eBay", None))
    if e:
        t.append(_site("eBay occasion", e.get("occasion")))
    if m:
        t.append(f"Prix de revente indiqué par défaut (milieu entre l'achat et le 2e vendeur) : {_eur(m.get('prix_revente'))} ; "
                 f"marge à ce prix sur Leboncoin : {_eur(m.get('marge_sans_charges'))} sans charges, {_eur(m.get('marge_avec_charges'))} avec charges de micro-entreprise")
    t.append("Frais des sites : Leboncoin et Vinted 0 % ; eBay 13 % + 0,35 € + port ; Amazon 15 % + 0,99 € + port.")
    return "\n".join(t)


def _texte(v, maxi=320):
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    return v[:maxi].rsplit(" ", 1)[0] + "…" if len(v) > maxi else v


def valider(f, d, regles):
    """Réponse de l'IA -> bilan propre, ou None si elle n'est pas exploitable. Les marges sont recalculées ici."""
    if not isinstance(d, dict) or not isinstance(d.get("expert"), dict) or not isinstance(d.get("acheteur"), dict):
        return None
    ex, ac = d["expert"], d["acheteur"]
    vendre, acheter = str(ex.get("vendre") or "").strip().upper()[:3], str(ac.get("acheter") or "").strip().upper()[:3]
    if vendre not in ("OUI", "NON") or acheter not in ("OUI", "NON") or not _texte(ex.get("raisons")) or not _texte(ac.get("raisons")):
        return None
    b = {"vendre": vendre == "OUI", "raisons_expert": _texte(ex.get("raisons")), "acheter": acheter == "OUI", "raisons_acheteur": _texte(ac.get("raisons"))}
    if b["vendre"]:
        canal = str(ex.get("ou") or "").strip().lower()
        try:
            prix = round(float(str(ex.get("prix")).replace(",", ".").replace("€", "").strip()), 2)
        except (TypeError, ValueError):
            return None
        if canal not in CANAUX or not (f["premier"] < prix < f["second"]):
            return None   # site inconnu ou prix hors des bornes : avis rejeté
        from .rentabilite import calculer
        try:
            avec = calculer(prix, canal, f["premier"], regles)
        except (KeyError, ValueError, ArithmeticError):
            return None
        b.update({"ou": canal, "prix": prix, "marge_avec_charges": avec["marge_nette"],
                  "marge_sans_charges": round(prix - f["premier"] - avec["frais_canal"], 2)})
    return b


def rediger(f, regles=None):
    """Bilan d'une affaire (dict) ou None. Un seul appel réussi ; les IA sont essayées dans l'ordre, une fois chacune."""
    from . import ia
    try:
        with open(os.path.join(RACINE, "config/equipe.json"), encoding="utf-8") as g:
            agents = json.load(g)["agents"]
        if regles is None:
            with open(os.path.join(RACINE, "config/regles.json"), encoding="utf-8") as g:
                regles = json.load(g)
    except (OSError, ValueError, KeyError):
        return None
    fiche = fiche_texte(f)
    for ident in ORDRE_IA:
        conf = agents.get(ident)
        if not conf:
            continue
        ag = ia.Agent(ident, {**conf, "max_appels": 1, "timeout": 45})
        if not ag.cle:
            continue
        b = valider(f, ia.extraire_json(ag.demander(SYSTEME, fiche)), regles)
        if b:
            b["ia"] = ag.nom
            return b
    return None


def lignes(f):
    """Lignes Telegram du bilan (vide s'il n'y en a pas)."""
    from html import escape
    b = f.get("bilan")
    if not b:
        return []
    t = ["", "🧑‍💼 <b>BILAN DE L'EXPERT</b>"]
    if b["vendre"]:
        t.append(f"✅ <b>Je le vends</b> : sur <b>{CANAUX[b['ou']]}</b> à <b>{_eur(b['prix'])}</b>"
                 f" → marge {_eur(b['marge_sans_charges'])} sans charges, {_eur(b['marge_avec_charges'])} avec charges micro")
    else:
        t.append("❌ <b>Je ne le vends pas</b>")
    t.append(escape(b["raisons_expert"], quote=False))
    t.append("🛒 <b>L'ACHETEUR devant l'annonce</b>")
    t.append(("✅ <b>Oui, j'achète</b> : " if b["acheter"] else "❌ <b>Non, je n'achète pas</b> : ") + escape(b["raisons_acheteur"], quote=False))
    return t
