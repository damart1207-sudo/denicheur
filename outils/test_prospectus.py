"""Sonde 4 : offres individuelles Bonial (images SEO-OFFER) — y a-t-il nom + prix structurés ? Lien du lecteur complet ?
Lancement : outil = test_prospectus"""
import re, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR"}
h = urllib.request.urlopen(urllib.request.Request("https://www.bonial.fr/Enseignes/Lidl", headers=H), timeout=40).read().decode("utf-8", "ignore")
i = h.find("SEO-OFFER")
print("OFFRE:", h[max(0, i - 1200):i + 600])
print("PRIX:", len(re.findall(r'"price"', h)), re.findall(r'"price"[^,]{0,80}', h)[:5])
print("VIEWER:", list(dict.fromkeys(re.findall(r'https://www\.bonial\.fr/[^"]*(?:Prospectus|prospectus|brochure|Catalogue)[^"]*', h)))[:10])
print("HREF:", list(dict.fromkeys(re.findall(r'"(?:url|href|link|deeplink)":"(https?://www\.bonial\.fr[^"]+)"', h)))[:15])
