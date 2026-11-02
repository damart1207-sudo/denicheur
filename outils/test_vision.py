"""Test : quelles IA lisent le mieux une annonce (image) ? 5 annonces piégées, vérité connue (annonces_test/verites.json).
Toutes les IA testées en version GRATUITE (OpenRouter : modèles ':free' uniquement). Aucune dépense.
Résultat : data/echantillons/test_vision2.json"""
import base64, json, os, re, time, urllib.request, urllib.error

DOSSIER = "outils/annonces_test"
CONSIGNE = ("Contexte : nous sommes le 2 novembre 2026 ; tous les produits cités existent bien et sont en vente. "
            "Les images sont des illustrations simplifiées pour un test : ne juge PAS le style du dessin, mais lis bien tout le texte écrit dessus. "
            "Tu es un expert anti-arnaque des petites annonces. Analyse cette capture d'annonce (photo + texte). "
            "Réponds UNIQUEMENT en JSON avec : produit (modèle exact), capacite, couleur, prix (nombre), etat, "
            "contradictions (liste : ce qui ne colle pas entre photo, titre et description), "
            "signaux_arnaque (liste), defauts (liste), verdict (un parmi : 'achat sûr', 'prudence', 'arnaque probable', 'contrefaçon probable'), "
            "explication (2 phrases en français). Regarde très attentivement le texte écrit sur la photo.")

FOURNISSEURS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
               None),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", None),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", None),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", None),
    "zai": ("https://api.z.ai/api/paas/v4", "ZAI_API_KEY", None),
}


def http(url, cle, corps=None, t=120):
    req = urllib.request.Request(url, data=json.dumps(corps).encode() if corps else None,
                                 headers={"Authorization": f"Bearer {cle}", "Content-Type": "application/json",
                                          "User-Agent": "denicheur/1.0"})
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read())


def modeles_vision(nom, base, cle):
    """Choisit automatiquement les modèles qui voient les images (gratuits)."""
    try:
        d = http(base + "/models", cle).get("data", [])
    except Exception as e:
        return [], f"liste impossible : {str(e)[:100]}"
    ids = [m.get("id", "") for m in d]
    res["tous"][nom] = ids[:200]
    if nom == "gemini":
        f = [i.split("/")[-1] for i in ids if re.search(r"flash", i) and not re.search(r"tts|image|audio|live|embed|preview-0", i)]
        return sorted(set(f), reverse=True)[:4], None
    if nom == "openrouter":
        ok = [m["id"] for m in d if m["id"].endswith(":free") and "image" in
              (m.get("architecture", {}).get("input_modalities") or [])]
        pref = [i for i in ok if re.search(r"qwen|llama-4|deepseek|gemma|mistral|kimi|glm|nemotron|intern", i)]
        return (pref or ok)[:6], None
    motif = {"groq": r"llama-4|vision|scout|maverick|vl|gemma|kimi", "nvidia": r"vision|vl|llama-4|scout|maverick|qwen.*vl|phi.*vision",
             "zai": r"glm-[\d.]+v|vision"}[nom]
    return [i for i in ids if re.search(motif, i, re.I)][:4], None


def image(nom):
    return "data:image/png;base64," + base64.b64encode(open(f"{DOSSIER}/{nom}.png", "rb").read()).decode()


res = {"tous": {}, "verites": json.load(open(f"{DOSSIER}/verites.json", encoding="utf-8")), "modeles": {}, "listes": {}}
for nom, (base, env, fixes) in FOURNISSEURS.items():
    cle = os.environ.get(env, "").strip()
    if not cle:
        res["listes"][nom] = "clé absente"
        continue
    mods, err = (fixes, None) if fixes else modeles_vision(nom, base, cle)
    res["listes"][nom] = err or mods
    for m in mods:
        r = res["modeles"][f"{nom}:{m}"] = {}
        for a in ["a1", "a2", "a3", "a4", "a5"]:
            corps = {"model": m, "temperature": 0.1, "messages": [{"role": "user", "content": [
                {"type": "text", "text": CONSIGNE}, {"type": "image_url", "image_url": {"url": image(a)}}]}]}
            t0 = time.time()
            try:
                d = http(base + "/chat/completions", cle, corps)
                r[a] = {"s": round(time.time() - t0, 1), "rep": (d["choices"][0]["message"].get("content") or "")[:2500]}
            except urllib.error.HTTPError as e:
                r[a] = {"erreur": f"HTTP {e.code} {e.read()[:150].decode(errors='replace')}"}
                if e.code == 429:
                    time.sleep(25)
                if e.code in (401, 402, 403, 404):
                    break
            except Exception as e:
                r[a] = {"erreur": str(e)[:150]}
            time.sleep(3)
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_vision2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res["listes"], ensure_ascii=False))
for k, v in res["modeles"].items():
    print(k, {a: ("OK" if "rep" in x else x["erreur"][:60]) for a, x in v.items()})
