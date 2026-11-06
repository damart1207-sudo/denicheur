"""Lecture seule de deux compteurs fournisseurs ; jamais de réponse brute ni de clé en sortie.

Ne modifie ni limites, ni registre, ni abonnement. N'exécute aucun Actor ou tâche SEO.
"""
import base64
from datetime import datetime, timezone
import json
import math
import os
import urllib.request


class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # ne transmet jamais Authorization vers une autre destination


def lire(url, autorisation):
    req = urllib.request.Request(url, method='GET', headers={
        'Authorization': autorisation, 'User-Agent': 'rebifftout-controle-comptes', 'Accept': 'application/json'})
    with urllib.request.build_opener(SansRedirection).open(req, timeout=20) as r:
        return json.loads(r.read(2_000_000))


def montant(v):
    return v if type(v) in (int, float) and math.isfinite(v) and v >= 0 else None


def resumer_dataforseo(d):
    if d.get('status_code') != 20000 or d.get('cost') != 0:
        return {'statut': 'reponse_non_validee'}
    t = (d.get('tasks') or [{}])[0]
    if t.get('status_code') != 20000 or t.get('cost') != 0:
        return {'statut': 'reponse_non_validee'}
    r = (t.get('result') or [{}])[0]
    jour = ((r.get('money') or {}).get('statistics') or {}).get('day') or {}
    compteurs = [montant(v) for k, v in jour.items() if k.startswith('total_')]
    # Le retour contient une période quotidienne, pas un relevé mensuel certifié.
    valide = bool(compteurs) and all(v is not None for v in compteurs)
    return {'statut': 'lecture_ok', 'compteur_journalier_disponible': valide,
            'rapprochement_mensuel': 'reste_a_faire', 'autorise_activation': False}


def resumer_apify(d):
    v = d.get('data') or {}
    usage = montant((v.get('current') or {}).get('monthlyUsageUsd'))
    plafond = montant((v.get('limits') or {}).get('maxMonthlyUsageUsd'))
    cycle = v.get('monthlyUsageCycle') or {}
    return {'statut': 'lecture_ok' if usage is not None else 'compteur_inconnu',
            'cycle_disponible': bool(cycle.get('startAt') and cycle.get('endAt')),
            'plafond_fournisseur_renseigne': plafond is not None,
            'plafond_fournisseur_atteint': usage >= plafond if usage is not None and plafond is not None else None,
            'rapprochement_cycle_et_mois_civil': 'reste_a_faire', 'autorise_activation': False}


def controler(environ=None):
    env = os.environ if environ is None else environ
    resultat = {'verifie_le': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'mode': 'GET_comptes_uniquement', 'autorise_activation': False}
    login, mdp, apify = (env.get(k, '').strip() for k in ('DATAFORSEO_LOGIN', 'DATAFORSEO_PASSWORD', 'APIFY_TOKEN'))
    appels = []
    resultat['dataforseo'] = {'statut': 'acces_non_configure'}
    resultat['apify'] = {'statut': 'acces_non_configure'}
    if login and mdp:
        auth = 'Basic ' + base64.b64encode((login + ':' + mdp).encode()).decode()
        appels.append(('dataforseo', 'https://api.dataforseo.com/v3/appendix/user_data', auth, resumer_dataforseo))
    if apify:
        appels.append(('apify', 'https://api.apify.com/v2/users/me/limits', 'Bearer ' + apify, resumer_apify))
    for nom, url, auth, resumer in appels:
        try:
            resultat[nom] = resumer(lire(url, auth))
        except Exception:
            # Les messages HTTP, réponses, logins et URLs signées restent privés.
            resultat[nom] = {'statut': 'lecture_impossible', 'autorise_activation': False}
    return resultat


if __name__ == '__main__':
    print(json.dumps(controler(), ensure_ascii=False, indent=2))
