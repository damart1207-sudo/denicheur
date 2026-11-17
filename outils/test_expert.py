"""Fiabilité de l'expert (denicheur/bilan.py) sur les VRAIES affaires du jour déjà étudiées (data/ecarts.json, marché complet).
Pour chacune : la grille du programme, puis l'avis de CHAQUE IA de l'équipe sur la même fiche (en parallèle), avec les avis
rejetés et pourquoi. Sert à classer les IA. Ensuite le bilan retenu part sur Telegram.
Coût : aucune recherche payante (données déjà relevées) ; Gemini quelques dixièmes de centime, les autres IA gratuites.
outil = test_expert"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from denicheur import bilan, ecart, ia, telegram

IAS = ("qwen", "gptoss", "nemotron_nv")
regles = ecart._lire(os.path.join(ecart.RACINE, "config/regles.json"), {})
agents = ecart._lire(os.path.join(ecart.RACINE, "config/equipe.json"), {})["agents"]
base = ecart._lire(ecart.F_ECARTS, {})
lot = [dict(f) for f in base.get("affaires", []) if (f.get("marche") or {}).get("leboncoin") is not None][:int(os.environ.get("NB", "4"))]
print(f"{len(lot)} affaires réelles avec marché complet ; formation : {len(bilan.formation())} caractères")
score = {i: [0, 0, 0.0] for i in IAS}


def avis(ident, systeme, fiche, f, g):
    conf = agents.get(ident)
    if not conf:
        return ident, None, "absente de l'équipe", 0
    ag = ia.Agent(ident, {**conf, "max_appels": 1, "timeout": 60})
    t0 = time.time()
    brut = ag.demander(systeme, fiche)
    d = ia.extraire_json(brut)
    b = bilan.valider(f, d, regles, g)
    if b and b["vendre"] and not g["vendable"]:
        b = None
    return ident, b, (" ; ".join(ag.erreurs) or ("réponse rejetée par la grille : " + json.dumps(d, ensure_ascii=False)[:400] if d else "réponse illisible : " + str(brut)[:200])) if not b else "", time.time() - t0


for f in lot:
    g = bilan.grille(f, regles)
    systeme, fiche = bilan.SYSTEME + "\n\nTA FORMATION :\n" + bilan.formation(), bilan.fiche_texte(f) + "\n\n" + bilan.grille_texte(g)
    print("\n" + "=" * 100 + "\n" + fiche)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for ident, b, erreur, duree in pool.map(lambda i: avis(i, systeme, fiche, f, g), IAS):
            score[ident][0] += 1
            score[ident][1] += bool(b)
            score[ident][2] += duree
            print(f"\n--- {ident} ({duree:.0f} s) : " + (json.dumps(b, ensure_ascii=False) if b else "PAS D'AVIS VALABLE — " + erreur))
    f["bilan"] = bilan.rediger(f, regles)
    print("\n>>> bilan retenu :", json.dumps({k: v for k, v in (f["bilan"] or {}).items() if k != "grille"}, ensure_ascii=False))
    texte = "🎓 Expert formé, avec 2e avis quand il dit oui\n" + ecart.message(f)
    print("Telegram :", telegram.envoyer(texte))
print("\nCLASSEMENT (avis valables / essais, durée moyenne) :")
for i, (n, ok, d) in sorted(score.items(), key=lambda x: (-x[1][1], x[1][2])):
    print(f"  {i} : {ok}/{n}, {d / max(n, 1):.0f} s")
