"""Appels aux IA (toutes compatibles avec le format OpenAI), avec garde-fous."""
import json
import os
import re
import time
import urllib.error
import urllib.request

TIMEOUT = 120  # secondes max par appel


class Agent:
    def __init__(self, ident, conf):
        self.id = ident
        self.conf = conf
        self.nom = conf["nom"]
        self.appels = 0
        self.erreurs = []
        self.duree = 0.0

    @property
    def cle(self):
        return os.environ.get(self.conf["cle_env"], "").strip()

    def disponible(self):
        return bool(self.cle) and self.appels < self.conf.get("max_appels", 5)

    def demander(self, systeme, message):
        """Renvoie le texte de la réponse, ou None (erreur notée). Jamais de boucle de relance."""
        if not self.cle:
            self.erreurs.append(f"secret {self.conf['cle_env']} absent")
            return None
        if self.appels >= self.conf.get("max_appels", 5):
            self.erreurs.append("plafond d'appels atteint")
            return None
        self.appels += 1
        corps = {
            "model": self.conf["modele"],
            "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": message}],
            "temperature": 0.2,
        }
        url = self.conf["base_url"].rstrip("/") + "/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(corps).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.cle}"},
        )
        t0 = time.time()
        for essai in (1, 2):  # au plus 1 seule relance, uniquement si surcharge
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    data = json.loads(r.read())
                self.duree += time.time() - t0
                return data["choices"][0]["message"].get("content") or ""
            except urllib.error.HTTPError as e:
                detail = e.read()[:200].decode(errors="replace")
                if e.code == 402:  # paiement exigé : on s'arrête net, jamais de dépense
                    self.erreurs.append("402 paiement exigé : agent coupé pour ce passage")
                    self.appels = 10**6
                    return None
                if e.code in (429, 503) and essai == 1:
                    time.sleep(20)
                    continue
                self.erreurs.append(f"HTTP {e.code}: {detail}")
                return None
            except Exception as e:
                self.erreurs.append(f"{type(e).__name__}: {e}"[:200])
                return None
        return None


def extraire_json(texte):
    """Récupère le premier objet JSON d'une réponse d'IA (tolère ```json et texte autour)."""
    if not texte:
        return None
    texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.S)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texte, flags=re.S)
    candidats = [m.group(1)] if m else []
    debut = texte.find("{")
    fin = texte.rfind("}")
    if debut != -1 and fin > debut:
        candidats.append(texte[debut:fin + 1])
    for c in candidats:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None
