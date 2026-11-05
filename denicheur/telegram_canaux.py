"""Lecture des chaînes Telegram PUBLIQUES de bons plans / erreurs de prix, sans compte ni clé :
la page web publique https://t.me/s/<chaîne> montre les derniers messages. Chaque message avec un prix devient une annonce.
Gratuit. Respecte les chaînes : lecture seule, une page par chaîne et par tour."""
import hashlib
import html
import re
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PRIX = re.compile(r"(\d{1,4}(?:[  .]\d{3})*(?:[,.]\d{1,2})?)\s?(?:€|euros?)", re.I)
ERREUR = re.compile(r"erreur de prix|price error|bug de prix|prix cass|-[6-9]\d\s?%|glitch", re.I)


def _texte(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<[^>]+>", " ", h)))).strip()


def lire(source, timeout=25):
    nom = source["chaine"]
    try:
        req = urllib.request.Request(f"https://t.me/s/{nom}", headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            h = r.read().decode("utf-8", "ignore")
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"[:200]
    out = []
    for m in re.finditer(r'data-post="([^"]+)".*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>.*?<time datetime="([^"]+)"', h, re.S):
        poste, corps, quand = m.group(1), m.group(2), m.group(3)
        t = _texte(corps)
        prix = PRIX.findall(t)
        if not prix:
            continue
        valeurs = []
        for p in prix:
            q = p.replace("\u00a0", " ").replace(" ", "")
            if re.search(r"[.,]\d{1,2}$", q):          # décimales : 25.99 / 25,99
                entier, dec = re.split(r"[.,](?=\d{1,2}$)", q)
                q = re.sub(r"[.,]", "", entier) + "." + dec
            else:                                       # milliers : 1.299 / 1 299
                q = re.sub(r"[.,]", "", q)
            try:
                valeurs.append(float(q))
            except ValueError:
                pass
        lieu = re.search(r"(\d[\d \u00a0.,]*\d)\s*(?:€|euros?)?\s*au lieu de\s*(\d[\d \u00a0.,]*\d)", t, re.I)
        if lieu:  # « 25.99 au lieu de 34.99€ » : le premier est le prix, le second l'ancien prix
            def _n(x):
                x = x.replace("\u00a0", "").replace(" ", "")
                return float(re.sub(r"[.,](?=\d{1,2}$)", ".", re.sub(r"[.,](?=\d{3}\b)", "", x)))
            try:
                valeurs = [_n(lieu.group(1)), _n(lieu.group(2))]
            except ValueError:
                pass
        if not valeurs:
            continue
        liens = re.findall(r'href="(https?://(?!t\.me)[^"]+)"', corps)
        titre = t.split("\n")[0][:160]
        out.append({"id": hashlib.sha1(poste.encode()).hexdigest()[:10], "titre": titre, "temperature": 600 if ERREUR.search(t) else 100,
                    "categorie": "", "marchand": "", "prix": min(valeurs), "devise": "EUR", "lien": liens[0] if liens else f"https://t.me/{poste}",
                    "date": quand[:16], "source": "telegram:" + nom, "pays": source.get("pays", "FR"),
                    "description": t[:300], "erreur_prix_signalee": bool(ERREUR.search(t)),
                    "prix_avant": max(valeurs) if len(valeurs) > 1 and max(valeurs) > min(valeurs) else None})
    return out[-40:], None
