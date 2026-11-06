"""Réservations avant dépense : fichier verrouillé localement ou registre GitHub CAS.

En Actions, aucun repli sur disque local : tous les runners partagent la branche
budget-api. Un appel incertain conserve sa réservation, même après un crash.
"""
import base64
import json
import os
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import urllib.error
import urllib.request

BRANCHE = 'budget-api'
FICHIER = 'registre-budgets.json'
RACINE = Path(__file__).resolve().parents[1]


class Indisponible(RuntimeError):
    pass


def micros(v):
    try:
        d = Decimal(str(v))
        if not d.is_finite() or d < 0:
            raise ValueError()
        return int((d * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    except Exception as e:
        raise ValueError('montant de budget invalide') from e


def verifier_etat(e):
    if not isinstance(e, dict) or not isinstance(e.get('services', {}), dict):
        raise Indisponible('format du registre invalide')
    for s in e.get('services', {}).values():
        if not isinstance(s, dict):
            raise Indisponible('format de service invalide')
        for cle in ('jours', 'mois', 'categories', 'reserves'):
            if not isinstance(s.get(cle), dict):
                raise Indisponible('compteurs incomplets')
        for cle in ('jours', 'mois', 'categories'):
            if any(type(v) is not int or v < 0 for v in s[cle].values()):
                raise Indisponible('compteur de dépense invalide')


@contextmanager
def verrou(chemin):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, 'a+b') as f:
        if os.name == 'nt':
            import msvcrt
            f.seek(0)
            f.write(b'0')
            f.flush()
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class Local:
    def __init__(self, chemin):
        self.chemin = Path(chemin)

    def modifier(self, fonction):
        with verrou(self.chemin.with_suffix('.lock')):
            try:
                etat = json.loads(self.chemin.read_text()) if self.chemin.exists() else {}
            except (OSError, ValueError) as e:
                raise Indisponible('registre local illisible, dépenses bloquées') from e
            verifier_etat(etat)
            resultat = fonction(etat)
            fd, nom = tempfile.mkstemp(dir=self.chemin.parent)
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(etat, f)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(nom, self.chemin)
            finally:
                if os.path.exists(nom):
                    os.unlink(nom)
            return resultat


class GitHub:
    def __init__(self, repo, token):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not token:
            raise Indisponible('registre partagé non configuré')
        self.base = 'https://api.github.com/repos/' + repo
        self.token = token

    def _api(self, route, data=None, method=None):
        req = urllib.request.Request(self.base + route,
            data=json.dumps(data).encode() if data is not None else None,
            method=method, headers={'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/vnd.github+json', 'User-Agent': 'rebifftout-budget'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    def modifier(self, fonction):
        # La branche doit être créée une fois avant activation, jamais remise à zéro.
        route = '/contents/' + FICHIER
        for _ in range(8):
            try:
                courant = self._api(route + '?ref=' + BRANCHE)
                etat = json.loads(base64.b64decode(courant['content']))
                sha = courant['sha']
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise Indisponible('registre partagé inaccessible') from None
                # Distinguer fichier absent et branche absente/droit insuffisant.
                try:
                    self._api('/git/ref/heads/' + BRANCHE)
                except Exception:
                    raise Indisponible('branche budget-api absente ou inaccessible') from None
                etat, sha = {}, None
            except Exception:
                raise Indisponible('registre partagé illisible') from None
            verifier_etat(etat)
            resultat = fonction(etat)
            data = {'message': 'Réservation ou rapprochement de budget', 'branch': BRANCHE,
                    'content': base64.b64encode(json.dumps(etat, sort_keys=True).encode()).decode()}
            if sha:
                data['sha'] = sha
            try:
                self._api(route, data, 'PUT')
                return resultat
            except urllib.error.HTTPError as e:
                if e.code not in (409, 422):
                    raise Indisponible('écriture du budget refusée') from None
                time.sleep(0.05)
            except Exception:
                # Un PUT incertain peut avoir réussi : ne jamais lancer la dépense.
                raise Indisponible('réservation non confirmée, dépense bloquée') from None
        raise Indisponible('conflits de budget persistants')


def stockage():
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        return GitHub(os.environ.get('GITHUB_REPOSITORY', ''), os.environ.get('BUDGET_GITHUB_TOKEN', ''))
    if os.environ.get('BUDGET_GITHUB_TOKEN'):
        return GitHub(os.environ.get('GITHUB_REPOSITORY', ''), os.environ['BUDGET_GITHUB_TOKEN'])
    return Local(RACINE / 'data/etat/budgets_v2.json')


def reserver(service, cout, plafond_jour, plafond_mois, *, categorie='', plafond_categorie=None,
             deja_jour=0, deja_mois=0, deja_categorie=0, backend=None):
    """Le plafond de l'appel est débité AVANT le POST. None = budget épuisé.

    Les anciennes dépenses servent de plancher de migration, jamais d'addition.
    Les montants sont des micro-dollars entiers pour éviter les erreurs d'arrondi.
    """
    jour = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    mois = jour[:7]
    ident = uuid.uuid4().hex
    cout = micros(cout)
    def modifier(e):
        services = e.setdefault('services', {})
        s = services.setdefault(service, {'jours': {}, 'mois': {}, 'categories': {}, 'reserves': {}})
        s['jours'][jour] = max(s['jours'].get(jour, 0), micros(deja_jour))
        s['mois'][mois] = max(s['mois'].get(mois, 0), micros(deja_mois))
        cle = jour + ':' + categorie
        s['categories'][cle] = max(s['categories'].get(cle, 0), micros(deja_categorie))
        if (s.get('bloque') or s['jours'][jour] + cout > micros(plafond_jour)
                or s['mois'][mois] + cout > micros(plafond_mois)
                or (plafond_categorie is not None and s['categories'][cle] + cout > micros(plafond_categorie))):
            return None
        s['jours'][jour] += cout
        s['mois'][mois] += cout
        s['categories'][cle] += cout
        s['reserves'][ident] = {'cout': cout, 'jour': jour, 'mois': mois, 'categorie': cle}
        return ident
    return (backend or stockage()).modifier(modifier)


def rapprocher(service, ident, cout_reel, *, backend=None):
    """Rapproche une seule fois. En cas d'échec réseau, la réserve reste débitée."""
    reel = micros(cout_reel)
    def modifier(e):
        s = e['services'][service]
        r = s['reserves'].pop(ident, None)
        if r is None:
            return  # rapprochement déjà enregistré
        delta = reel - r['cout']
        for k, cle in [('jours', r['jour']), ('mois', r['mois']), ('categories', r['categorie'])]:
            s[k][cle] += delta
        if delta > 0:
            s['bloque'] = True  # le tarif dépasse l'estimation : arrêter avant le prochain appel
    (backend or stockage()).modifier(modifier)
