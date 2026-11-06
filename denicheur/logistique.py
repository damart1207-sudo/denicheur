"""Preuves de livraison liées à l'offre : ni domaine marchand ni drapeau historique.

Le total automatique nécessite un port EUR explicite pour toute la France,
une TVA explicitement incluse et une origine d'expédition dans l'UE.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

UE = set('AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE'.split())


def montant(v):
    if isinstance(v, bool):
        return None
    try:
        n = Decimal(str(v))
        return float(n.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) if n.is_finite() and n >= 0 else None
    except Exception:
        return None


def _liste(x):
    return x if isinstance(x, list) else [x]


def depuis_offre(detail, lien, date=None):
    """N'infère rien d'un nom de pays du deal, d'un domaine ou de mots génériques."""
    if not detail:
        return None
    o = detail['offre']
    if any(o.get(k) for k in ('validForMemberTier', 'eligibleQuantity', 'eligibleTransactionVolume')):
        return None
    candidates = []
    for s in _liste(o.get('shippingDetails', [])):
        if not isinstance(s, dict):
            continue
        regions = _liste(s.get('shippingDestination', []))
        fr = [r for r in regions if isinstance(r, dict) and 'FR' in _liste(r.get('addressCountry'))]
        if not fr:
            continue
        if s.get('doesNotShip') is True:
            return None
        if any(any(r.get(k) for k in ('postalCode', 'addressRegion', 'postalCodePrefix', 'postalCodeRange', 'hasCertification')) for r in fr):
            continue  # un tarif local ne prouve pas une livraison France entière
        if any(s.get(k) for k in ('validForMemberTier', 'shippingLabel', 'shippingSettingsLink', 'eligibleTransactionVolume')):
            continue
        taux = s.get('shippingRate') or {}
        if not isinstance(taux, dict) or taux.get('currency') != 'EUR':
            continue
        if taux.get('@type') not in (None, 'MonetaryAmount') or any(k in taux for k in ('minValue', 'maxValue', 'freeShippingThreshold')):
            continue
        port = montant(taux.get('value'))
        if port is None:
            continue  # une fourchette ou un tarif conditionnel ne vaut pas un montant exact
        origine = s.get('shippingOrigin') or {}
        pays = origine.get('addressCountry') if isinstance(origine, dict) else None
        if not isinstance(pays, str):
            pays = None
        candidates.append((port, pays))
    if len(set(candidates)) != 1:
        return None
    port, pays = candidates[0]
    specs = _liste(o.get('priceSpecification', []))
    # Le marqueur TVA doit appartenir au prix courant, jamais à une recommandation.
    pertinents = [s for s in specs if isinstance(s, dict)
                  and (s.get('price') is None or montant(s['price']) == detail['prix'])
                  and s.get('priceCurrency', 'EUR') == 'EUR']
    tva = bool(pertinents) and all(s.get('valueAddedTaxIncluded') is True for s in pertinents)
    return {'lien': lien, 'verifie_le': date or datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'source': 'jsonld-offre', 'pays_destination': 'FR', 'devise': 'EUR',
            'prix_article': detail['prix'], 'port': port, 'pays_expedition': pays,
            'tva_incluse': tva,
            'total': montant(Decimal(str(detail['prix'])) + Decimal(str(port))) if tva and pays in UE else None}


def etat(x):
    from .validation import recent, url_produit, meme_prix
    p = x.get('preuve_livraison') or {}
    if not isinstance(p, dict):
        return {'livraison': False, 'total': None}
    lien = x.get('lien_marchand') or (x.get('page_offre') or {}).get('lien_marchand') or x.get('lien')
    port = montant(p.get('port'))
    valide = (p.get('source') in ('jsonld-offre', 'controle-marchand')
              and p.get('pays_destination') == 'FR' and p.get('devise') == 'EUR'
              and x.get('devise', 'EUR') == 'EUR' and recent(p.get('verifie_le'))
              and url_produit(lien) and url_produit(p.get('lien')) == url_produit(lien)
              and meme_prix(p.get('prix_article'), x.get('prix')) and port is not None)
    total = p.get('total')
    complet = bool(valide and p.get('tva_incluse') is True and isinstance(p.get('pays_expedition'), str) and p['pays_expedition'] in UE
                   and meme_prix(total, montant(Decimal(str(x['prix'])) + Decimal(str(port)))))
    return {'livraison': bool(valide), 'total': total if complet else None}


def appliquer(x, preuve=None):
    """Met à jour les champs compatibles seulement à partir d'une preuve valide."""
    if preuve is not None:
        x['preuve_livraison'] = preuve
    e = etat(x)
    x['livraison_fr_confirmee'] = e['livraison']
    x['cout_total_confirme'] = e['total'] is not None
    if e['total'] is not None:
        x['cout_achat'] = e['total']
    return e
