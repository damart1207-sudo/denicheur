"""BILAN d'une affaire « écart vendeurs » (demande de David, 17/11/2026), ajouté à la fin de chaque alerte Telegram :
 1. l'avis d'un EXPERT e-commerce : je vends ce produit ou non ; si oui, où et à quel prix ;
 2. l'avis d'un ACHETEUR placé devant l'annonce à ce prix : j'achète ou non, et pourquoi.

Fiabilité (17/11/2026, David : « es-tu sûr que ton expert s'y connaît ? ») : le PROGRAMME calcule d'abord une grille
(`grille`) : demande, prix de vente maximum (5 % sous le neuf le moins cher visible), marges, refus automatiques. L'IA reçoit
sa formation (skills/expert_revente.md) et cette grille ; un avis qui la contredit est rejeté. Sans IA valable, le programme
écrit lui-même un refus chiffré, jamais un « oui ».
Une IA rédige les deux avis à partir des SEULS chiffres relevés (prix, ventes, volume de recherche, comparateurs,
annonces Leboncoin / Vinted / eBay et leur ancienneté). Garde-fous : aucun chiffre accepté de l'IA en dehors du prix de
vente conseillé, lui-même borné entre notre achat et le 2e vendeur (sens inverse : entre le coût de l'annonce neuve et le
moins cher d'Amazon, jamais revendu sur Amazon) ; les deux marges à ce prix sont recalculées ici
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
{"expert": {"vendre": "OUI" ou "NON", "achat": "amazon" | "vinted" | "ebay", "ou": "leboncoin" | "vinted" | "ebay" | "amazon" | null, "prix": nombre ou null, "raisons": "..."},
 "acheteur": {"acheter": "OUI" ou "NON", "raisons": "..."}}

Rôle 1, EXPERT e-commerce : décide si tu revends ce produit. Si OUI : le site où il partira le mieux et UN prix de vente en euros,
strictement entre le prix d'achat et le prix du 2e vendeur. Dis NON si la demande est faible (peu de ventes, peu de recherches),
si le produit est déjà affiché à ton prix d'achat dans les comparateurs, si des annonces moins chères existent déjà,
ou si des annonces traînent depuis des semaines sans se vendre.
Deux sens sont possibles, choisis le meilleur et indique-le dans « achat » : (a) acheter sur Amazon au prix d'achat de la fiche et revendre
ailleurs, prix de vente strictement entre ce prix d'achat et le 2e vendeur ; (b) seulement si la fiche contient une ligne « Sens inverse » :
acheter l'annonce neuve indiquée (vinted ou ebay) et revendre en neuf sur leboncoin, vinted ou ebay, JAMAIS sur amazon (Amazon exige une
facture de fournisseur pour vendre du neuf), prix de vente strictement entre le coût de cette annonce et le prix le moins cher d'Amazon.
Rôle 2, ACHETEUR : tu es devant l'annonce de ce produit au prix conseillé par l'expert (ou au prix de revente indiqué si l'expert
dit NON), sur le site choisi. Tu compares avec ce que tu trouves en deux minutes : comparateurs, Amazon, autres annonces.
Dis si tu achètes, OUI ou NON, et pourquoi.

La demande se juge d'abord sur les ventes Amazon (50 achats ou plus par mois = forte, moins de 15 ventes sur 30 jours = faible),
ensuite sur les recherches Google ; un volume « trop peu pour être mesuré » ou « inconnu » ne prouve pas à lui seul une demande faible.
Sous la fiche, une GRILLE calculée par le programme donne le niveau de demande, le prix de vente maximum et les marges : tiens-la pour
exacte. Ton prix ne dépasse jamais ce prix de vente maximum. Si la grille refuse un sens, tu ne le choisis pas ; si elle refuse la vente,
tu réponds NON. Si tu réponds OUI, ajoute dans « expert » le champ "condition" : en une phrase, ce qui ferait rater la vente.
L'ACHETEUR voit l'offre Amazon au prix d'achat de la fiche tant qu'elle est en ligne : dis-le si ça le fait renoncer.
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
    from .marche import inverse
    inv = inverse(f)
    if inv:
        t.append(f"Sens inverse : une annonce NEUVE à {_eur(inv['prix'])} sur {inv['site']} (coût {_eur(inv['cout'])} frais d'achat compris, hors port)"
                 + (f", en ligne depuis {inv['age']} jours" if inv.get("age") is not None else "")
                 + f", soit {_eur(inv['ecart'])} sous le moins cher d'Amazon ({_eur(f.get('premier'))})")
    if m:
        t.append(f"Prix de revente indiqué par défaut (milieu entre l'achat et le 2e vendeur) : {_eur(m.get('prix_revente'))} ; "
                 f"marge à ce prix sur Leboncoin : {_eur(m.get('marge_sans_charges'))} sans charges, {_eur(m.get('marge_avec_charges'))} avec charges de micro-entreprise")
    t.append("Frais des sites : Leboncoin et Vinted 0 % ; eBay 13 % + 0,35 € + port ; Amazon 15 % + 0,99 € + port.")
    return "\n".join(t)


MARGE_MIN = 20     # euros sans charges : en dessous, on ne vend pas (objectif de David : environ 30 € par vente)
SOUS_LE_NEUF = 0.95   # prix de vente maximum : 5 % sous le neuf le moins cher que l'acheteur peut trouver


def grille(f, regles):
    """Ce que le PROGRAMME calcule avant l'avis de l'IA (un calcul d'IA n'est jamais une preuve) : niveau de demande,
    prix de vente maximum réaliste, marges à ce prix, refus automatiques (« vetos »), sens inverse possible ou non."""
    from .marche import inverse
    from .rentabilite import calculer
    mk = f.get("marche") or {}
    ventes, achetes = f.get("ventes_estimees_30j") or 0, f.get("achetes_mois_amazon") or 0
    demande = "forte" if achetes >= 50 or ventes >= 30 else "moyenne" if achetes or ventes >= 10 else "faible"
    c = mk.get("comparateur_min")
    c = c if c and c["prix"] >= 0.7 * f["premier"] else None
    v, e = mk.get("vinted") or {}, mk.get("ebay") or {}
    neufs = [(f"une annonce neuve {n}", r["min"]) for n, r in (("Vinted", v.get("neuf")), ("eBay", e.get("neuf"))) if r and r.get("nb")]
    refs = [("le 2e vendeur Amazon", f["second"])] + ([(f"le comparateur {c['ou']}", c["prix"])] if c else []) + neufs
    ref_nom, ref_prix = min(refs, key=lambda r: r[1])
    plafond = round(ref_prix * SOUS_LE_NEUF, 2)

    def marges(prix, cout):
        try:
            return round(prix - cout, 2), calculer(prix, "leboncoin", cout, regles)["marge_nette"]
        except (KeyError, ValueError, ArithmeticError):
            return round(prix - cout, 2), None
    sans, avec = marges(plafond, f["premier"])
    vetos = []
    if c and c["prix"] <= f["premier"] * 1.05:
        vetos.append(f"il est déjà affiché à {_eur(c['prix'])} sur {c['ou']}, ton prix d'achat : n'importe qui le trouve à ce prix")
    if sans < MARGE_MIN:
        vetos.append(f"en vendant 5 % sous {ref_nom} ({_eur(ref_prix)}), soit {_eur(plafond)}, il reste {_eur(sans)} de marge, moins de {MARGE_MIN} €")
    occ = [(r["min"], n) for n, r in (("Leboncoin", mk.get("leboncoin")), ("Vinted", v), ("eBay occasion", e.get("occasion"))) if r and r.get("nb")]
    dates = [r for r in (mk.get("leboncoin"), e.get("neuf"), e.get("occasion")) if r and r.get("dates")]
    g = {"demande": demande, "ref_nom": ref_nom, "ref_prix": ref_prix, "plafond": plafond, "marge_sans": sans, "marge_avec": avec,
         "vetos": vetos, "annonce_min": min(occ) if occ else None,
         "anciennes": sum(r["anciennes"] for r in dates), "datees": sum(r["dates"] for r in dates), "inverse": None}
    inv = inverse(f)
    if inv:
        autres = [("le moins cher d'Amazon", f["premier"])] + ([(f"le comparateur {c['ou']}", c["prix"])] if c else []) \
            + [r for r in neufs if not (r[0].lower().endswith(inv["site"]) and r[1] == inv["prix"])]
        nom_i, prix_i = min(autres, key=lambda r: r[1])
        plafond_i = round(prix_i * SOUS_LE_NEUF, 2)
        sans_i, avec_i = marges(plafond_i, inv["cout"])
        g["inverse"] = {**inv, "ref_nom": nom_i, "ref_prix": prix_i, "plafond": plafond_i, "marge_sans": sans_i, "marge_avec": avec_i,
                        "possible": sans_i >= MARGE_MIN}
    g["vendable"] = not vetos or bool(g["inverse"] and g["inverse"]["possible"])
    return g


def grille_texte(g):
    t = ["GRILLE CALCULÉE PAR LE PROGRAMME (chiffres sûrs, à ne pas recalculer) :",
         f"- Demande : {g['demande']}",
         f"- Sens normal (achat sur Amazon) : prix de vente maximum {_eur(g['plafond'])} (5 % sous {g['ref_nom']} à {_eur(g['ref_prix'])}) ; "
         f"marge à ce prix sur Leboncoin ou Vinted : {_eur(g['marge_sans'])} sans charges, {_eur(g['marge_avec'])} avec charges micro"]
    if g["vetos"]:
        t.append("- SENS NORMAL REFUSÉ PAR LE PROGRAMME : " + " ; ".join(g["vetos"]))
    i = g["inverse"]
    if i:
        t.append(f"- Sens inverse (achat de l'annonce neuve {i['site']} à {_eur(i['prix'])}, coût {_eur(i['cout'])}) : prix de vente maximum "
                 f"{_eur(i['plafond'])} (5 % sous {i['ref_nom']} à {_eur(i['ref_prix'])}) ; marge {_eur(i['marge_sans'])} sans charges, "
                 f"{_eur(i['marge_avec'])} avec charges micro" + ("" if i["possible"] else " : REFUSÉ PAR LE PROGRAMME (marge trop faible)"))
    if g["annonce_min"]:
        t.append(f"- Annonce la moins chère tous états confondus : {_eur(g['annonce_min'][0])} sur {g['annonce_min'][1]}")
    if g["datees"]:
        t.append(f"- Annonces datées : {g['anciennes']} sur {g['datees']} sont en ligne depuis plus de 21 jours")
    if not g["vendable"]:
        t.append("=> Le programme REFUSE la vente. Réponds vendre = NON et explique pourquoi avec ces chiffres.")
    return "\n".join(t)


def _texte(v, maxi=320):
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    return v[:maxi].rsplit(" ", 1)[0] + "…" if len(v) > maxi else v


def valider(f, d, regles, g=None):
    """Réponse de l'IA -> bilan propre, ou None si elle contredit la grille ou n'est pas exploitable. Marges recalculées ici."""
    g = g or grille(f, regles)
    if not isinstance(d, dict) or not isinstance(d.get("expert"), dict) or not isinstance(d.get("acheteur"), dict):
        return None
    ex, ac = d["expert"], d["acheteur"]
    vendre, acheter = str(ex.get("vendre") or "").strip().upper()[:3], str(ac.get("acheter") or "").strip().upper()[:3]
    if vendre not in ("OUI", "NON") or acheter not in ("OUI", "NON") or not _texte(ex.get("raisons")) or not _texte(ac.get("raisons")):
        return None
    b = {"vendre": vendre == "OUI", "raisons_expert": _texte(ex.get("raisons")), "acheter": acheter == "OUI", "raisons_acheteur": _texte(ac.get("raisons"))}
    if b["vendre"]:
        from .rentabilite import calculer
        canal, achat, inv = str(ex.get("ou") or "").strip().lower(), str(ex.get("achat") or "amazon").strip().lower(), g["inverse"]
        try:
            prix = round(float(str(ex.get("prix")).replace(",", ".").replace("€", "").strip()), 2)
        except (TypeError, ValueError):
            return None
        if achat == "amazon" and not g["vetos"]:
            cout, haut = f["premier"], g["plafond"]
        elif inv and inv["possible"] and achat == inv["site"] and canal != "amazon":
            cout, haut = inv["cout"], inv["plafond"]   # sens inverse : jamais revendu sur Amazon
            b.update({"achat": achat, "prix_achat": inv["prix"], "cout_achat": cout})
        else:
            return None   # sens refusé par la grille : avis rejeté
        if canal not in CANAUX or not (cout < prix <= haut):
            return None   # site inconnu, ou prix au-dessus du maximum de la grille : avis rejeté
        try:
            avec = calculer(prix, canal, cout, regles)
        except (KeyError, ValueError, ArithmeticError):
            return None
        b.update({"ou": canal, "prix": prix, "marge_avec_charges": avec["marge_nette"],
                  "marge_sans_charges": round(prix - cout - avec["frais_canal"], 2)})
        if b["marge_sans_charges"] < MARGE_MIN:
            return None   # frais du site compris, la marge passe sous le minimum
    b["condition"] = _texte(ex.get("condition"), 200) if b["vendre"] else ""
    return b


def sans_ia(f, g):
    """Bilan écrit par le programme seul quand aucune IA ne rend un avis valable : la grille décide, sans phrase inventée."""
    acheteur = (False, f"Tant que l'offre à {_eur(f['premier'])} reste en ligne sur Amazon, je l'achète là-bas : livraison et retour garantis.")
    if not g["vendable"] or g["demande"] == "faible" or (not g["vetos"] and g["marge_sans"] < 30 and not (g["inverse"] and g["inverse"]["possible"])):
        raison = (g["vetos"][0] if g["vetos"] else "le produit se vend trop peu sur Amazon pour partir vite" if g["demande"] == "faible"
                  else f"au prix maximum de {_eur(g['plafond'])}, la marge n'est que de {_eur(g['marge_sans'])}")
        return {"vendre": False, "raisons_expert": ("Non : " + raison + ".")[:320], "acheter": acheteur[0], "raisons_acheteur": acheteur[1], "ia": "programme"}
    return None   # un OUI n'est jamais donné sans avis rédigé


def formation():
    try:
        with open(os.path.join(RACINE, "skills/expert_revente.md"), encoding="utf-8") as g:
            return g.read()
    except OSError:
        return ""


def rediger(f, regles=None, ordre=ORDRE_IA):
    """Bilan d'une affaire (dict) ou None. Les IA sont essayées dans l'ordre, une fois chacune ; la grille du programme tranche."""
    from . import ia
    try:
        with open(os.path.join(RACINE, "config/equipe.json"), encoding="utf-8") as h:
            agents = json.load(h)["agents"]
        if regles is None:
            with open(os.path.join(RACINE, "config/regles.json"), encoding="utf-8") as h:
                regles = json.load(h)
    except (OSError, ValueError, KeyError):
        return None
    g = grille(f, regles)
    systeme, fiche = SYSTEME + "\n\nTA FORMATION :\n" + formation(), fiche_texte(f) + "\n\n" + grille_texte(g)
    for ident in ordre:
        conf = agents.get(ident)
        if not conf:
            continue
        ag = ia.Agent(ident, {**conf, "max_appels": 1, "timeout": 45})
        if not ag.cle:
            continue
        b = valider(f, ia.extraire_json(ag.demander(systeme, fiche)), regles, g)
        if b and b["vendre"] and not g["vendable"]:
            b = None
        if b:
            b.update({"ia": ag.nom, "grille": g})
            return b
    b = sans_ia(f, g)
    if b:
        b["grille"] = g
    return b


def lignes(f):
    """Lignes Telegram du bilan (vide s'il n'y en a pas)."""
    from html import escape
    b = f.get("bilan")
    if not b:
        return []
    t = ["", "🧑‍💼 <b>BILAN DE L'EXPERT</b>"]
    g = b.get("grille")
    if g:
        t.append(f"Demande {g['demande']} · prix de vente maximum réaliste : <b>{_eur(g['plafond'])}</b> (5 % sous {escape(g['ref_nom'])}, {_eur(g['ref_prix'])})"
                 f" → marge {_eur(g['marge_sans'])} sans charges")
    if b["vendre"]:
        if b.get("achat"):
            t.append(f"🔄 En l'achetant sur <b>{CANAUX[b['achat']]}</b> à {_eur(b['prix_achat'])} (annonce neuve), pas sur Amazon")
        t.append(f"✅ <b>Je le vends</b> : sur <b>{CANAUX[b['ou']]}</b> à <b>{_eur(b['prix'])}</b>"
                 f" → marge {_eur(b['marge_sans_charges'])} sans charges, {_eur(b['marge_avec_charges'])} avec charges micro")
    else:
        t.append("❌ <b>Je ne le vends pas</b>")
    t.append(escape(b["raisons_expert"], quote=False))
    if b.get("condition"):
        t.append("⚠️ Ce qui ferait tout rater : " + escape(b["condition"], quote=False))
    t.append("🛒 <b>L'ACHETEUR devant l'annonce</b>")
    t.append(("✅ <b>Oui, j'achète</b> : " if b["acheter"] else "❌ <b>Non, je n'achète pas</b> : ") + escape(b["raisons_acheteur"], quote=False))
    return t
