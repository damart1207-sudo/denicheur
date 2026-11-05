"""Diagnostic : ManoMano répond-il à GitHub ? Lancement : outil = test_verif_prix"""
import urllib.request, re
U = "https://www.manomano.fr/p/makita-ls1019l-scie-a-onglet-radiale-avec-laser-1510w-260-x-30mm-24014748"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR"}
try:
    r = urllib.request.urlopen(urllib.request.Request(U, headers=H), timeout=30); h = r.read().decode("utf-8", "ignore")
    print("STATUT", r.status, len(h), "ld+json:", h.count("ld+json"), "price:", re.findall(r'"price"\s*:\s*"?[\d.,]+', h)[:5])
except Exception as e:
    print("STATUT", e)
