"""CLASSEMENTS DU JOUR (demande de David, 04/11) : chaque jour, le top 10 de ce qui s'est le plus vendu aux USA, au Japon,
au Royaume-Uni et en Chine, photographié à 23 h 59 HEURE LOCALE de chaque pays, envoyé sur Telegram.
Le lendemain, David part à la chasse en France sur ces produits.

USA / Japon / Royaume-Uni : meilleures ventes Amazon (Keepa) des grandes catégories ; le rang Amazon est recalculé
toutes les heures sur les ventes récentes, donc le n° 1 d'une catégorie à 23 h 59 = le produit qui a le plus vendu ce jour-là.
Classement : position dans la catégorie, puis ventes du mois (« achetés le mois dernier »). Pour chaque produit :
déjà vendu en France ? à quel prix ? combien de vendeurs ?
Chine : pas de chiffres de ventes accessibles depuis le cloud -> les bons plans les plus populaires de SMZDM (le Dealabs chinois).
Coût : ≈ 500 jetons Keepa par pays et par jour (compris dans l'abonnement).
Appelé à chaque tour de veille ; ne fait quelque chose que dans la fenêtre 23 h 40 - 01 h 00 locale, une fois par jour et par pays."""
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D_SORTIE = os.path.join(RACINE, "data/classements")
F_ETAT = os.path.join(RACINE, "data/etat/classements.json")
FUSEAUX = {"US": "America/New_York", "JP": "Asia/Tokyo", "UK": "Europe/London", "CN": "Asia/Shanghai"}
NOMS = {"US": "🇺🇸 USA", "JP": "🇯🇵 Japon", "UK": "🇬🇧 Royaume-Uni", "CN": "🇨🇳 Chine"}
TAUX = {"US": 0.90, "JP": 0.0058, "UK": 1.17, "CN": 0.125}
UK_RACINES = ("electronics", "toys", "video games", "beauty", "home", "kitchen", "sports", "computers", "baby", "pet")


def _lire(f, d):
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return d


def _ecrire(f, d):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def jour_a_photographier(pays, maintenant=None):
    """Date locale du classement si on est dans la fenêtre 23 h 40 - 01 h 00 locale, sinon None."""
    loc = (maintenant or datetime.now(timezone.utc)).astimezone(ZoneInfo(FUSEAUX[pays]))
    if loc.hour == 23 and loc.minute >= 40:
        return loc.strftime("%Y-%m-%d")
    if loc.hour == 0:
        return (loc - timedelta(days=1)).strftime("%Y-%m-%d")
    return None


def _eur(p, pays):
    if not isinstance(p, (int, float)) or p <= 0:
        return None
    return round(p * (100 if pays == "JP" else 1) * TAUX[pays], 2)


JETONS_CLASSEMENT = 700   # ≈ 8 catégories × 50 + fiches : à garder en réserve avant chaque photo de 23 h 59
F_RESERVE_TEST = os.path.join(RACINE, "data/etat/reserve_keepa.json")


def reserve_keepa(maintenant=None):
    """Jetons que la moisson doit laisser : JETONS_CLASSEMENT pendant l'heure qui précède une photo et pendant la fenêtre,
    tant que le classement du pays n'est pas fait (et pendant un test demandé via data/etat/reserve_keepa.json)."""
    now = maintenant or datetime.now(timezone.utc)
    t = _lire(F_RESERVE_TEST, {})
    if t.get("jusqua", "") > now.isoformat():
        return int(t.get("jetons", JETONS_CLASSEMENT))
    etat = _lire(F_ETAT, {})
    for pays in ("US", "JP", "UK"):
        for avance in (0, 60):
            d = jour_a_photographier(pays, now + timedelta(minutes=avance))
            if d and etat.get(pays) != d:
                return JETONS_CLASSEMENT
    return 0


def categories(pays):
    from . import moisson
    if pays in moisson.CATEGORIES_HYPE:
        return moisson.CATEGORIES_HYPE[pays][:8]
    f = os.path.join(RACINE, f"data/base/keepa_categories_{pays}.json")
    cats = _lire(f, None)
    if cats is None:
        d = moisson._appel("category", {"domain": moisson.DOMAINES[pays], "category": 0, "parents": 0})
        cats = [(int(k), v.get("name")) for k, v in (d.get("categories") or {}).items()
                if any(m in (v.get("name") or "").lower() for m in UK_RACINES)]
        _ecrire(f, cats)
    return [tuple(c) for c in cats][:8]


def amazon(pays, n=10, par_cat=10):
    from . import moisson
    pos = {}
    for cat, nom in categories(pays):
        try:
            d = moisson._appel("bestsellers", {"domain": moisson.DOMAINES[pays], "category": cat})
        except Exception:
            continue
        for i, a in enumerate(((d.get("bestSellersList") or {}).get("asinList") or [])[:par_cat], 1):
            pos.setdefault(a, (i, nom))
    if not pos:
        return []
    labas = {r["asin"]: r for r in moisson.fiches(list(pos)[:100], pays)}
    lst = []
    for a, (i, nom) in pos.items():
        r = labas.get(a)
        if not r:
            continue
        croissance = round((r["r90"] / r["r30"] - 1) * 100) if r.get("r30") and r.get("r90") else None
        lst.append({"asin": a, "titre": r.get("t"), "categorie": nom, "position": i, "vendus_mois": r.get("vendus_mois"),
                    "prix_eur": _eur(r.get("neuf"), pays), "croissance_ventes_pct": croissance, "rang": r.get("rang")})
    lst.sort(key=lambda x: (x["position"], -(x["vendus_mois"] or 0)))
    top = lst[:n]
    ici = {r["asin"]: r for r in moisson.fiches([x["asin"] for x in top], "FR")}
    for x in top:
        r = ici.get(x["asin"])
        x["france"] = ({"prix": r.get("neuf"), "rang": r.get("rang"), "vendeurs": r.get("offres"), "vendus_mois": r.get("vendus_mois")}
                       if r and r.get("neuf") else None)
        x["lien"] = f"https://www.amazon.{ {'US': 'com', 'JP': 'co.jp', 'UK': 'co.uk'}[pays] }/dp/{x['asin']}"
    return top


def chine(n=10, date=None):
    """SMZDM : les bons plans les plus récents du jour (pas de chiffres de ventes) ; titres traduits par Gemini."""
    pc = _lire(os.path.join(RACINE, "data/pc/annonces.json"), {}).get("annonces", [])
    jd = sorted([x for x in pc if str(x.get("source", "")).startswith("pc:jd-")], key=lambda x: x.get("rang") or 99)
    if jd:  # vrai classement des ventes JD.com, lu par le PC de David
        lst = jd[:n]
        source = "jd"
    else:
        flux = _lire(os.path.join(RACINE, "data/hype_flux.json"), {}).get("titres", [])
        lst = [x for x in flux if str(x.get("source", "")).startswith("smzdm")][-n:]
        source = "smzdm"
    if not lst:
        return []
    try:
        from .ia import Agent, extraire_json
        conf = _lire(os.path.join(RACINE, "config/equipe.json"), {}).get("agents", {}).get("gemini")
        rep = Agent("gemini", {**conf, "max_appels": 1, "timeout": 90}).demander(
            "Tu traduis des titres de produits chinois en français. JSON uniquement.",
            'Traduis chaque titre en français court (marque + produit). Format {"t": ["...", ...]} dans le même ordre.\n'
            + "\n".join(x["titre"] for x in lst)) if conf else None
        tr = (extraire_json(rep) or {}).get("t") if rep else None
    except Exception:
        tr = None
    return [{"titre": (tr[i] if tr and i < len(tr) else x["titre"]), "original": x["titre"], "lien": x.get("lien"), "source": source,
             "prix_eur": round(x["prix"] * TAUX["CN"], 2) if source == "jd" and isinstance(x.get("prix"), (int, float)) else None}
            for i, x in enumerate(lst)]


def message(pays, date, top):
    from .telegram import _e, _eur as eur
    if pays == "CN":
        if top and top[0].get("source") == "jd":
            lignes = [f"<b>{NOMS[pays]} — top 10 des ventes JD.com du {date}</b> (classement JD lu par ton PC)"]
        else:
            lignes = [f"<b>{NOMS[pays]} — les 10 bons plans les plus populaires du {date}</b> (SMZDM, pas de chiffres de ventes)"]
        lignes += [f"{i}. {_e(x['titre'])}" + (f" · {eur(x['prix_eur'])}" if x.get("prix_eur") else "") + f"\n{_e(x.get('lien'))}"
                   for i, x in enumerate(top, 1)]
        return "\n".join(lignes)
    lignes = [f"<b>{NOMS[pays]} — top 10 des ventes Amazon du {date}</b> (photo à 23 h 59 heure locale)"]
    for i, x in enumerate(top, 1):
        fr = x.get("france")
        fr_t = ("🇫🇷 <b>absent d'Amazon France</b> → à chasser" if not fr else
                f"🇫🇷 en France : {eur(fr['prix'])}, {fr.get('vendeurs') if fr.get('vendeurs') is not None else '?'} vendeurs"
                + (f", {fr['vendus_mois']} vendus/mois" if fr.get("vendus_mois") else ""))
        cr = x.get("croissance_ventes_pct")
        lignes.append(f"\n{i}. <b>{_e((x.get('titre') or '')[:80])}</b>\n"
                      f"n° {x['position']} en {_e(x['categorie'])} · {eur(x.get('prix_eur'))}"
                      + (f" · {x['vendus_mois']} vendus le mois dernier" if x.get("vendus_mois") else "")
                      + (f" · ventes {'📈 +' if cr >= 0 else '📉 '}{cr} % (30 j vs 90 j)" if cr is not None else "")
                      + f"\n{fr_t}\n{_e(x['lien'])}")
    return "\n".join(lignes)


def tour(forcer=None):
    """À chaque tour de veille. forcer = code pays pour tester hors fenêtre."""
    from . import telegram
    etat = _lire(F_ETAT, {})
    faits = []
    for pays in (FUSEAUX if not forcer else [forcer]):
        date = jour_a_photographier(pays) if not forcer else datetime.now(timezone.utc).astimezone(ZoneInfo(FUSEAUX[pays])).strftime("%Y-%m-%d")
        if not date or etat.get(pays) == date:
            continue
        top = chine(date=date) if pays == "CN" else amazon(pays)
        if not top:
            continue
        _ecrire(os.path.join(D_SORTIE, pays, date + ".json"), {"pays": pays, "date": date, "top": top})
        texte = message(pays, date, top)
        paquet = ""
        for bloc in texte.split("\n\n"):
            if len(paquet) + len(bloc) > 3800:
                telegram.envoyer(paquet)
                paquet = ""
            paquet += bloc + "\n\n"
        if paquet.strip():
            telegram.envoyer(paquet)
        etat[pays] = date
        _ecrire(F_ETAT, etat)
        faits.append(pays)
    return faits
