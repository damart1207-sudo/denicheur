"""Telegram : messages à David (robot @BotFather, secrets TELEGRAM_TOKEN et TELEGRAM_CHAT_ID). Gratuit.
Silencieux tant que les secrets ne sont pas posés. Jamais de message vide ni d'excuse technique (skills/rapport.md).
python -m denicheur.telegram "texte"   -> envoie un message de test"""
import json
import os
import sys
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pret():
    return bool(os.environ.get("TELEGRAM_TOKEN", "").strip() and os.environ.get("TELEGRAM_CHAT_ID", "").strip())


def envoyer(texte, html=True):
    """Envoie un message (≤ 4 000 caractères, coupé sinon). Renvoie True si parti."""
    if not pret() or not texte:
        return False
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN'].strip()}/sendMessage"
    corps = {"chat_id": os.environ["TELEGRAM_CHAT_ID"].strip(), "text": texte[:4000], "disable_web_page_preview": True}
    if html:
        corps["parse_mode"] = "HTML"
    req = urllib.request.Request(url, data=urllib.parse.urlencode(corps).encode(), headers={"User-Agent": "denicheur/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        if html:  # une balise mal fermée ? on renvoie en texte brut
            return envoyer(texte, html=False)
        return False


def envoyer_fichier(chemin, legende=""):
    """Envoie un fichier (ex. data/rapport_david.html) en pièce jointe : David l'ouvre sur son téléphone."""
    if not pret() or not os.path.isfile(chemin):
        return False
    import uuid
    limite = uuid.uuid4().hex
    nom = os.path.basename(chemin)
    corps = b""
    for k, v in (("chat_id", os.environ["TELEGRAM_CHAT_ID"].strip()), ("caption", legende[:1000])):
        corps += f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    corps += f"--{limite}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{nom}\"\r\nContent-Type: text/html\r\n\r\n".encode()
    corps += open(chemin, "rb").read() + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN'].strip()}/sendDocument", data=corps,
                                 headers={"Content-Type": f"multipart/form-data; boundary={limite}", "User-Agent": "denicheur/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False


def _e(t):
    return str(t if t is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _eur(v):
    return f"{v:.2f} €".replace(".", ",") if isinstance(v, (int, float)) else "—"


def rapport_passage(resultat, lien_rapport=None):
    """Résumé d'un passage : seulement les cartes vertes et orange, signées. Rien n'est envoyé s'il n'y en a aucune."""
    cartes = [c for c in resultat.get("candidats", []) if c.get("feu") in ("vert", "orange")]
    if not cartes:
        return False
    feux = {"vert": "🟢", "orange": "🟠"}
    lignes = [f"<b>Dénicheur — passage {_e(resultat.get('passage'))} du {_e(resultat.get('date_affichee'))}</b>",
              f"{sum(1 for c in cartes if c['feu'] == 'vert')} verte(s), {sum(1 for c in cartes if c['feu'] == 'orange')} orange"]
    for c in cartes[:12]:
        den = "Radar Keepa" if str(c.get("id", "")).startswith("keepa-") else "Idéfix"
        pmin = (c.get("prix_plancher") or {}).get("prix_min")
        lignes.append(f"\n{feux[c['feu']]} <b>{_e(c.get('nom_produit') or c.get('titre'))}</b> — {den}{' · BINGO' if c.get('bingo') else ''}\n"
                      f"achat {_eur(c.get('prix'))} chez {_e(c.get('marchand'))} ({_e(c.get('pays'))}) · neuf {_eur(pmin)} · "
                      f"revente {_eur(c.get('prix_revente_prudent'))} · marge <b>{_eur(c.get('marge_verifiee'))}</b>"
                      + (f" · concurrents Amazon : {c['vendeurs_amazon']} vendeurs" if c.get('vendeurs_amazon') is not None else "")
                      + f"\n🔗 Annonce la moins chère : {_e(c.get('lien'))}"
                      + (f"\n🔗 Moins cher en France : {_e((c.get('prix_plancher') or {}).get('lien'))}" if (c.get("prix_plancher") or {}).get("lien") else ""))
    if lien_rapport:
        lignes.append(f"\nRapport complet : {_e(lien_rapport)}")
    return envoyer("\n".join(lignes))


def alerte(x, vol=None):
    """Une annonce = une fiche de décision complète (denicheur/fiche.py). Rouge : rien n'est envoyé."""
    from . import fiche
    f = fiche.evaluer(x, vol)
    x["fiche"] = f
    if f["feu"] == "rouge":
        return False
    if f["feu"] == "vert" and (x.get("controle_prix") or {}).get("statut") not in ("ok", "different"):
        f["feu"] = "orange"
        f["manque"] = f["manque"] + ["prix non revérifié sur la fiche"]
    rond = {"vert": "🟢 <b>VERT</b> — l'affaire tient", "orange": "🟠 <b>ORANGE</b> — à confirmer"}[f["feu"]]
    def n(v):
        return f"{v:,}".replace(",", " ") if isinstance(v, int) else "inconnu"
    conc = f["vendeurs"]
    conc_t = "inconnue" if conc is None else f"{conc} vendeurs " + ("(faible)" if conc <= 4 else "(moyenne)")
    texte = (("🚨 <b>ERREUR DE PRIX PROBABLE</b> — commander 1 unité tout de suite\n" if x.get("erreur_prix_probable") else "")
             + f"{rond}\n<b>{_e(x.get('nom_produit') or x.get('titre'))}</b> — {_e(x.get('denicheur') or 'Idéfix')}\n"
             f"💶 Prix le plus bas trouvé : <b>{_eur(f['achat'])}</b> chez {_e(x.get('marchand'))} ({_e(x.get('pays'))}), port compris\n"
             f"🏷️ Neuf le moins cher ailleurs : {_eur(f['neuf_min'])} ({_e(f['neuf_ou'])})"
             + (f" → {f['ecart_pct']} % moins cher" if f['ecart_pct'] is not None else "") + "\n"
             f"⚔️ Concurrence : {conc_t}\n"
             f"🔎 Recherches Google : {n(f['volume'])} /mois · ventes Amazon 30 jours : {n(f['ventes_30j'])}\n"
             f"♻️ Occasion : " + (f"de {_eur(f['occ_bas'])} à {_eur(f['occ_haut'])}" if f['occ_bas'] is not None else "inconnue") + "\n"
             f"🎯 Prix d'achat maximum : {_eur(f['achat_max'])} · revendre sur <b>{_e(f['vendre_sur'])}</b> à {_eur(f['prix_vente'])}\n"
             f"💰 Bénéfice net : <b>{_eur(f['benefice'])}</b>\n"
             + (f"🎯 Probabilité de vendre en 7 jours : <b>{f['proba_vente_7j']} %</b> ({_e(' · '.join(f['proba_detail']))}) — estimation\n"
                if f.get("proba_vente_7j") is not None else "")
             + (f"⚠️ Bloque le vert : {_e(', '.join(f['manque']))}\n" if f['manque'] else "")
             + (f"ℹ️ À compléter (ne bloque pas) : {_e(', '.join(f.get('a_completer') or []))}\n" if f.get('a_completer') else "")
             + ("✅ Prix vérifié sur la fiche du produit\n" if (x.get("controle_prix") or {}).get("statut") == "ok"
                else f"🔁 Prix corrigé d'après la fiche : {_eur((x.get('controle_prix') or {}).get('prix_page'))} (annoncé {_eur(x.get('prix_annonce_initial'))})\n"
                if (x.get("controle_prix") or {}).get("statut") == "different"
                else "⚠️ Prix non revérifié sur la fiche : contrôle-le avant d'acheter\n")
             + f"🔗 Annonce la moins chère : {_e(x.get('lien'))}"
             + (f"\n🔗 Moins cher en France : {_e(f['neuf_lien'])}" if f.get("neuf_lien") else ""))
    return envoyer(texte)

def plus_recherches(n=15):
    """Les produits les plus recherchés sur Google en France (volumes DataForSEO, data/bingo.json), avec la concurrence."""
    try:
        b = json.load(open(os.path.join(RACINE, "data/bingo.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    m = sorted([x for x in b.get("meilleurs", []) if x.get("recherches_mois")], key=lambda x: -x["recherches_mois"])[:n]
    if not m:
        return False
    def conc(x):
        v = x.get("vendeurs")
        if v is None:
            return "concurrence inconnue"
        return ("🟢 peu" if v <= 4 else "🟠 moyenne" if v <= 9 else "🔴 forte") + f" ({v} vendeurs Amazon)"
    lignes = [f"<b>🔎 Les plus recherchés en France (Google, par mois)</b> — mise à jour du {_e(str(b.get('maj', ''))[:10])}"]
    for i, x in enumerate(m, 1):
        lignes.append(f"\n{i}. <b>{_e(x.get('mot_cle'))}</b>{' · 💎 BINGO' if x.get('bingo') else ''}\n"
                      f"{x['recherches_mois']:,} recherches/mois".replace(",", " ")
                      + f" · prix Amazon {_eur(x.get('prix'))} · {conc(x)}"
                      + (f" · ventes Amazon 30 jours ≈ {x['ventes_30j']}" if x.get("ventes_30j") is not None else ""))
    lignes.append("\n🟢 peu de vendeurs = bonne occasion · 🔴 beaucoup = on évite sauf prix bien plus bas")
    return envoyer("\n".join(lignes))


if __name__ == "__main__":
    print("envoyé" if envoyer(" ".join(sys.argv[1:]) or "Test du robot Dénicheur : ça marche.") else "non envoyé (secrets absents ou erreur)")
