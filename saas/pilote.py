"""Poste de contrôle local, sans réseau, achat ou notification.

python saas/pilote.py --ouvrir
Les données historiques sont des hypothèses, pas des ordres d'achat.
"""
import argparse
from datetime import datetime
from decimal import Decimal, ROUND_CEILING
import html
import json
import math
from pathlib import Path
import re
import sys
import webbrowser

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
from denicheur.logistique import etat
from denicheur.rentabilite import calculer, DEFAUT
from denicheur.validation import blocages, url_produit


def nombre(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0


def prix_minimum(cout, canal, regles, objectif=20):
    """Arrondi au centime supérieur : le seuil doit atteindre l'objectif."""
    p = regles['plateformes_revente'][canal]
    f = {**DEFAUT, **regles.get('fiscalite', {})}
    taux = sum(Decimal(str(f[k])) for k in ('cotisations', 'versement_liberatoire', 'formation_professionnelle'))
    denom = 1 - taux - Decimal(str(p['commission']))
    if not nombre(cout) or denom <= 0 or objectif < 0:
        raise ValueError('hypothèses invalides')
    montant = sum(Decimal(str(v)) for v in (cout, p['frais_fixes'], p['port'], f['provision_incident_eur'], objectif)) / denom
    return float(montant.quantize(Decimal('.01'), rounding=ROUND_CEILING))


def modeles(titre):
    return set(re.findall(r'\b[A-Z]+[A-Z0-9]*\d[A-Z0-9]*(?:[-+][A-Z0-9]+)*\b', (titre or '').upper()))


def examiner(x, regles, canal='leboncoin', objectif=20):
    raisons = blocages(x)
    titre = x.get('nom_produit') or x.get('titre') or 'Sans titre'
    keepa = (x.get('keepa') or {}).get('titre')
    if keepa and modeles(titre) - modeles(keepa):
        raisons.append('référence Keepa différente ou incomplète : rapprochement à contrôler')
    total = etat(x)['total']
    cout = total if total is not None else x.get('cout_achat')
    vente = next((c.get('prix_vente') for c in (x.get('canaux') or [])
                  if isinstance(c, dict) and c.get('canal') == canal), None)
    # Ne réutilise jamais une marge historique ni une simple mention « validé ».
    detail = None
    if x.get('devise', 'EUR') == 'EUR' and nombre(cout) and nombre(vente):
        detail = calculer(vente, canal, cout, regles)
    else:
        raisons.append('coût ou hypothèse de vente EUR manquant')
    raisons.append('prix de vente historique : confirmer des ventes conclues du même produit et du même état')
    raisons.append('éligibilité du compte et du produit au canal à confirmer')
    marge = detail['marge_nette'] if detail else None
    return {'id': str(x.get('id', '')), 'titre': titre, 'marchand': x.get('marchand') or '',
            'lien': url_produit(x.get('lien_marchand') or (x.get('page_offre') or {}).get('lien_marchand') or x.get('lien')),
            'historique': x.get('statut') or '', 'date': x.get('trouve_le') or '',
            'cout': cout if nombre(cout) else None, 'cout_confirme': total is not None,
            'vente': vente if nombre(vente) else None, 'marge': marge,
            'minimum': prix_minimum(cout, canal, regles, objectif) if nombre(cout) and x.get('devise', 'EUR') == 'EUR' else None,
            'statut': 'À écarter selon hypothèses' if marge is not None and marge < objectif else 'À vérifier',
            'raisons': raisons, 'calcul': detail}


def construire(annonces, regles, canal='leboncoin', objectif=20):
    lignes = [examiner(x, regles, canal, objectif) for x in annonces if isinstance(x, dict)]
    lignes.sort(key=lambda x: x['marge'] if x['marge'] is not None else -float('inf'), reverse=True)
    modele = Path(__file__).with_name('pilote_modele.html').read_text(encoding='utf-8')
    # JSON incorporé non exécutable ; les titres externes ne peuvent fermer le script.
    donnees = json.dumps({'offres': lignes, 'regles': regles, 'canal': canal, 'objectif': objectif}, ensure_ascii=False, allow_nan=False)
    donnees = donnees.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return modele.replace('@@DONNEES@@', donnees).replace('@@DATE@@', html.escape(datetime.now().astimezone().strftime('%d/%m/%Y %H:%M %Z')))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ouvrir', action='store_true')
    p.add_argument('--canal', choices=['leboncoin', 'ebay', 'rebifftout'], default='leboncoin')
    p.add_argument('--objectif', type=float, default=20)
    p.add_argument('--sortie', type=Path, default=RACINE / 'data/test/pilote.html')
    args = p.parse_args()
    if not math.isfinite(args.objectif) or args.objectif < 0:
        p.error('objectif positif ou nul requis')
    annonces = json.loads((RACINE / 'data/alertes.json').read_text(encoding='utf-8'))
    regles = json.loads((RACINE / 'config/regles.json').read_text(encoding='utf-8'))
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(construire(annonces, regles, args.canal, args.objectif), encoding='utf-8')
    print(f'{len(annonces)} pistes ; aucun appel réseau. Rapport : {args.sortie.resolve()}')
    if args.ouvrir:
        webbrowser.open(args.sortie.resolve().as_uri())
