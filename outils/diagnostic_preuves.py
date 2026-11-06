"""Diagnostic gratuit des preuves. Sans écriture dans data/, IA, API payante ou Telegram.

--relire relit au plus trois fiches marchandes (GET publics). Aucune commande.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from denicheur.validation import blocages
from denicheur.logistique import appliquer
from denicheur.verif_prix import controler


def diagnostic(annonces, relire=False):
    raisons = Counter()
    exemples = []
    verifiees = 0
    for x in annonces:
        x = dict(x)
        if relire and verifiees < 3 and (x.get('lien_marchand') or (x.get('page_offre') or {}).get('lien_marchand')):
            v = controler(x, timeout=12)
            x['controle_prix'] = v
            if v.get('statut') == 'ok':
                appliquer(x, v.get('preuve_livraison'))
            verifiees += 1
        erreurs = blocages(x)
        raisons.update(erreurs)
        if len(exemples) < 5:
            exemples.append({'id': x.get('id'), 'produit': x.get('nom_produit') or x.get('titre'),
                             'blocages': erreurs})
    return {'offres_examinees': len(annonces), 'fiches_relues': verifiees,
            'controle_prix': 'maximum 3 GET marchands' if relire else 'sans réseau',
            'blocages': dict(raisons), 'exemples': exemples}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--relire', action='store_true')
    args = p.parse_args()
    racine = Path(__file__).resolve().parents[1]
    xs = json.loads((racine / 'data/alertes.json').read_text())
    print(json.dumps(diagnostic(xs, args.relire), ensure_ascii=False, indent=2))
