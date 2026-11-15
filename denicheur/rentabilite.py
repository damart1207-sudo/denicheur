"""Contribution par commande, après prélèvements et provision, avant frais mensuels.

Les taux sont des hypothèses configurables, pas une détermination du régime fiscal.
Le prix de vente inclut toutes les sommes encaissées (y compris le port facturé).
"""
from decimal import Decimal, ROUND_HALF_UP

VERSION = 2
DEFAUT = {"cotisations": 0.123, "versement_liberatoire": 0.01,
          "formation_professionnelle": 0.001, "provision_incident_eur": 3.0}


def _d(v):
    d = Decimal(str(v))
    if not d.is_finite() or d < 0:
        raise ValueError("montant ou taux invalide")
    return d


def _euros(v):
    return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculer(prix, plateforme, cout, regles):
    """Refuse les canaux inconnus au lieu de leur appliquer le tarif Amazon."""
    p = regles["plateformes_revente"][plateforme]
    fiscal = {**DEFAUT, **regles.get("fiscalite", {})}
    vente, achat = _d(prix), _d(cout)
    taux = sum((_d(fiscal[k]) for k in ("cotisations", "versement_liberatoire", "formation_professionnelle")), Decimal(0))
    commission = _d(p["commission"])
    if taux + commission >= 1:
        raise ValueError("prélèvements et commission doivent rester sous 100 %")
    frais = vente * commission + _d(p["frais_fixes"]) + _d(p["port"])
    prelevements = vente * taux
    provision = _d(fiscal["provision_incident_eur"])
    return {"version": VERSION, "prix_vente": _euros(vente), "cout_achat": _euros(achat),
            "frais_canal": _euros(frais), "prelevements": _euros(prelevements),
            "provision": _euros(provision), "marge_nette": _euros(vente - achat - frais - prelevements - provision),
            "perimetre": "après prélèvements et provision, avant frais mensuels et temps de travail"}
