"""Test sur 9 VRAIES annonces Leboncoin / Vinted (texte complet + photos). Gratuit.
Résultat : data/echantillons/test_vision_reel.json"""
import base64, json, os, time, urllib.request, urllib.error

A = json.load(open("outils/annonces_reelles/annonces.json", encoding="utf-8"))
CONSIGNE = ("Nous sommes le 2 novembre 2026. Voici une VRAIE annonce de petites annonces (texte complet ci-dessous + photos jointes). "
            "Tu es un expert anti-arnaque et un acheteur-revendeur expérimenté. Examine très attentivement CHAQUE photo "
            "(modèle exact visible, état, rayures, accessoires, texte/étiquettes, photo de catalogue ou vraie photo) et le texte. "
            "Réponds UNIQUEMENT en JSON : produit_identifie (modèle exact, en t'appuyant sur les photos), ce_que_montrent_les_photos (liste), "
            "etat_reel, coherence_photos_texte (liste des incohérences ou 'aucune'), signaux_positifs (liste), signaux_negatifs (liste), "
            "questions_a_poser_au_vendeur (liste), verdict ('achat sûr', 'prudence', 'arnaque probable', 'contrefaçon probable'), "
            "explication (3 phrases en français).\n\nANNONCE :\n")
FOURN = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
               ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", ["nvidia/nemotron-3.5-super-vl:free"]),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", ["meta/llama-3.2-90b-vision-instruct"]),
}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
      "Referer": "https://www.vinted.fr/"}


def charger(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            b = r.read()
            typ = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return f"data:{typ};base64," + base64.b64encode(b).decode(), len(b)
    except Exception as e:
        return None, str(e)[:80]


res = {"images": {}, "modeles": {}}
images = {}
for a in A:
    images[a["id"]] = []
    for u in a["imgs"][:4]:
        d, info = charger(u)
        res["images"].setdefault(a["id"], []).append(info)
        if d:
            images[a["id"]].append(d)
for nom, (base, env, mods) in FOURN.items():
    cle = os.environ.get(env, "").strip()
    for m in mods:
        r = res["modeles"][f"{nom}:{m}"] = {}
        for a in A:
            imgs = images[a["id"]] if nom != "nvidia" else images[a["id"]][:1]  # llama 3.2 : 1 image max
            contenu = [{"type": "text", "text": CONSIGNE + a["texte"]}] + [{"type": "image_url", "image_url": {"url": i}} for i in imgs]
            corps = {"model": m, "temperature": 0.1, "messages": [{"role": "user", "content": contenu}]}
            req = urllib.request.Request(base + "/chat/completions", data=json.dumps(corps).encode(),
                                         headers={"Authorization": f"Bearer {cle}", "Content-Type": "application/json", "User-Agent": "denicheur/1.0"})
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=150) as rr:
                    d = json.loads(rr.read())
                r[a["id"]] = {"s": round(time.time() - t0, 1), "nb_photos": len(imgs), "rep": d["choices"][0]["message"].get("content") or ""}
            except urllib.error.HTTPError as e:
                r[a["id"]] = {"erreur": f"HTTP {e.code} {e.read()[:150].decode(errors='replace')}"}
                if e.code in (401, 403, 404):
                    break
                if e.code == 429:
                    time.sleep(30)
            except Exception as e:
                r[a["id"]] = {"erreur": str(e)[:150]}
            time.sleep(4)
os.makedirs("data/echantillons", exist_ok=True)
json.dump(res, open("data/echantillons/test_vision_reel.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res["images"]))
for k, v in res["modeles"].items():
    print(k, {a: ("OK" if "rep" in x else x["erreur"][:50]) for a, x in v.items()})
