import json
from playwright.sync_api import sync_playwright

CSS = """body{margin:0;font-family:Arial,sans-serif;background:#f4f4f4;width:900px}
.c{background:#fff;margin:16px;border-radius:10px;overflow:hidden;border:1px solid #ddd}
.ph{height:380px;background:#e9edf1;display:flex;align-items:center;justify-content:center}
.b{padding:18px 22px}.t{font-size:24px;font-weight:bold;margin:0 0 6px}.p{font-size:28px;color:#e05a00;font-weight:bold;margin:4px 0 10px}
.m{color:#555;font-size:15px;margin:2px 0}.d{margin-top:14px;font-size:16px;line-height:1.45;white-space:pre-line}
.v{margin-top:14px;padding:10px;border-top:1px solid #eee;font-size:15px;color:#333}.hd{background:#2b3a4a;color:#fff;padding:8px 22px;font-size:14px}"""

def phone(label, couleur="#f6f6f6", crack=False):
    c = '<path d="M300 300 L330 270 L345 295 L370 262" stroke="#333" stroke-width="2" fill="none"/><path d="M330 270 L320 240" stroke="#333" stroke-width="1.5" fill="none"/>' if crack else ''
    return f'''<svg width="560" height="360"><rect x="40" y="20" width="230" height="320" rx="14" fill="#fff" stroke="#aaa"/>
<text x="155" y="150" font-size="22" text-anchor="middle" font-family="Arial" fill="#222">{label}</text>
<text x="155" y="185" font-size="13" text-anchor="middle" fill="#777">Boîte scellée</text>
<rect x="320" y="30" width="160" height="310" rx="26" fill="{couleur}" stroke="#333" stroke-width="3"/>
<rect x="332" y="50" width="136" height="270" rx="14" fill="#111"/>{c}</svg>'''

ANN = [
 dict(id="a1", titre="iPhone 17 256 Go Blanc - NEUF sous blister", prix="549 €", lieu="Lyon 69003", date="Aujourd'hui 09:12",
      photo=phone("iPhone 17 · 128GB · White"),
      desc="iPhone 17 256 Go blanc neuf jamais ouvert, cadeau en double.\nPaiement par virement bancaire uniquement, pas de remise en main propre.\nEnvoi rapide dès réception du virement. Répondez par mail : bonplan.tel77@gmail.com",
      vendeur="Particulier · Membre depuis octobre 2026 · 0 avis",
      verite={"produit":"iPhone 17","capacite_annonce":"256 Go","capacite_photo":"128 Go (contradiction)","prix":549,"pieges":["capacité de la boîte (128GB) ≠ titre (256 Go)","paiement par virement uniquement hors plateforme","contact par e-mail hors plateforme","compte créé récemment, 0 avis","prix ~25 % sous le neuf"],"verdict":"arnaque probable"}),
 dict(id="a2", titre="PS5 Slim avec lecteur disque + 1 manette", prix="299 €", lieu="Nantes 44000", date="Hier 18:40",
      photo='<svg width="560" height="360"><rect x="200" y="20" width="110" height="320" rx="20" fill="#fafafa" stroke="#333" stroke-width="3"/><rect x="250" y="20" width="10" height="320" fill="#222"/><text x="420" y="150" font-size="20" text-anchor="middle" font-family="Arial">PS5 Slim</text><text x="420" y="180" font-size="18" text-anchor="middle" font-family="Arial" fill="#c00">DIGITAL EDITION</text><text x="420" y="210" font-size="13" text-anchor="middle" fill="#666">(sans lecteur disque)</text></svg>',
      desc="Vends PS5 Slim très bon état, achetée en 2025.\nVersion avec lecteur disque, parfaite pour les jeux physiques.\n1 manette DualSense incluse, câbles d'origine.\nRemise en main propre ou envoi avec paiement sécurisé.",
      vendeur="Particulier · Membre depuis 2019 · 37 avis ★ 4,8",
      verite={"produit":"PS5 Slim","prix":299,"pieges":["l'étiquette de la photo indique DIGITAL EDITION (sans lecteur) alors que la description dit avec lecteur"],"verdict":"prudence (contradiction à clarifier)"}),
 dict(id="a3", titre="Aspirateur Dyson V15 Detect Absolute - garantie 2027", prix="320 €", lieu="Bordeaux 33000", date="Aujourd'hui 11:05",
      photo='<svg width="560" height="360"><rect x="250" y="40" width="40" height="230" fill="#7a3fa0"/><circle cx="270" cy="70" r="40" fill="#f2c200" stroke="#555"/><rect x="200" y="270" width="140" height="40" rx="10" fill="#555"/><text x="420" y="160" font-size="20" font-family="Arial" text-anchor="middle">Dyson V15 Detect</text><text x="420" y="190" font-size="14" text-anchor="middle" fill="#666">Facture + accessoires</text></svg>',
      desc="Dyson V15 Detect Absolute acheté en mars 2025 chez Darty, facture disponible.\nGarantie constructeur jusqu'en mars 2027.\nTous les accessoires, batterie en parfait état (60 min).\nPaiement sécurisé via le site ou main propre.",
      vendeur="Particulier · Membre depuis 2016 · 124 avis ★ 4,9",
      verite={"produit":"Dyson V15 Detect Absolute","prix":320,"pieges":[],"verdict":"achat sûr (annonce cohérente)"}),
 dict(id="a4", titre="AirPods Pro 2 NEUFS boîte scellée", prix="89 €", lieu="Paris 75018", date="Aujourd'hui 07:30",
      photo='<svg width="560" height="360"><rect x="170" y="60" width="220" height="220" rx="30" fill="#fff" stroke="#999"/><text x="280" y="170" font-size="22" text-anchor="middle" font-family="Comic Sans MS, cursive">AirPod Pro</text><text x="280" y="200" font-size="12" text-anchor="middle" fill="#888">High Quality · Compatible</text></svg>',
      desc="AirPods Pro 2 neufs, qualité premium, compatible iPhone et Android.\nRéduction de bruit active, boîtier de charge.\nStock disponible : 10 pièces. Livraison depuis l'étranger 15-20 jours.",
      vendeur="Professionnel · Membre depuis septembre 2026 · 3 avis ★ 3,1",
      verite={"produit":"écouteurs type AirPods Pro 2","prix":89,"pieges":["prix ~65 % sous le neuf","boîte « AirPod Pro » mal orthographiée, mention « Compatible / High Quality » = contrefaçon","10 pièces en stock + livraison étranger 15-20 j"],"verdict":"contrefaçon probable"}),
 dict(id="a5", titre="Samsung Galaxy S25 Ultra 512 Go Titane Noir", prix="780 €", lieu="Marseille 13008", date="Hier 21:15",
      photo=phone("Galaxy S25 Ultra · 512 Go", couleur="#2a2a2a", crack=True),
      desc="Galaxy S25 Ultra 512 Go, très peu servi.\nPetite fissure dans le coin en bas de l'écran, n'affecte pas l'utilisation.\nVersion Hong Kong double SIM. Chargeur non fourni (câble seul).\nPaiement sécurisé accepté.",
      vendeur="Particulier · Membre depuis 2018 · 52 avis ★ 4,7",
      verite={"produit":"Samsung Galaxy S25 Ultra 512 Go","prix":780,"pieges":["écran fissuré (visible sur la photo et indiqué)","version Hong Kong (import, garantie FR absente)","chargeur non fourni"],"verdict":"prudence (défauts réels, prix à revoir)"}),
]
verites = {}
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 900})
    for a in ANN:
        h = f'''<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="c"><div class="hd">Petites annonces · Électronique</div>
<div class="ph">{a["photo"]}</div><div class="b"><p class="t">{a["titre"]}</p><p class="p">{a["prix"]}</p>
<p class="m">{a["lieu"]} · {a["date"]}</p><div class="d">{a["desc"]}</div><div class="v">{a["vendeur"]}</div></div></div></body></html>'''
        pg.set_content(h); pg.locator(".c").screenshot(path=f'{a["id"]}.png'); verites[a["id"]] = a["verite"]
    b.close()
json.dump(verites, open("verites.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok")
