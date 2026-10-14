"""Publie sur Instagram le prochain post dont la date est arrivée.

Lit posts.json, ignore ceux déjà dans posted-log.json, publie le plus ancien
dont la date est <= aujourd'hui (heure de Bruxelles), puis l'ajoute au journal.

Variables d'environnement :
  IG_TOKEN          jeton d'accès Instagram (secret GitHub)
  IG_USER_ID        identifiant du compte Instagram
  GITHUB_REPOSITORY fourni automatiquement par GitHub Actions (ex. moi/depot)
  BRANCH            branche du dépôt (défaut : main)
  DRY_RUN=1         simule sans rien publier
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

API = "https://graph.instagram.com/v25.0"
HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts.json")
LOG = os.path.join(HERE, "posted-log.json")


def call(method, path, params):
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        url, data = f"{url}?{data.decode()}", None
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Erreur API Instagram ({e.code}) : {e.read().decode()}")


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    today = datetime.now(ZoneInfo("Europe/Brussels")).date().isoformat()
    posts = load(POSTS, [])
    log = load(LOG, [])
    done = {entry["id"] for entry in log}

    due = sorted((p for p in posts if p["id"] not in done and p["date"] <= today),
                 key=lambda p: p["date"])
    if not due:
        print(f"Rien à publier aujourd'hui ({today}).")
        return
    post = due[0]

    repo = os.environ.get("GITHUB_REPOSITORY", "UTILISATEUR/DEPOT")
    branch = os.environ.get("BRANCH", "main")
    image_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{post['image']}"
    print(f"Post « {post['id']} » → {image_url}")

    if os.environ.get("DRY_RUN") == "1":
        print("DRY_RUN : rien n'est publié.")
        media_id = "dry-run"
    else:
        token = os.environ["IG_TOKEN"]
        user = os.environ["IG_USER_ID"]

        # 1. conteneur
        container = call("POST", f"{user}/media", {
            "image_url": image_url,
            "caption": post["caption"],
            "access_token": token,
        })["id"]

        # 2. attendre qu'il soit prêt (étape obligatoire)
        for _ in range(20):
            status = call("GET", container, {"fields": "status_code",
                                             "access_token": token}).get("status_code")
            if status == "FINISHED":
                break
            if status == "ERROR":
                sys.exit("Instagram a refusé l'image (status ERROR).")
            time.sleep(3)
        else:
            sys.exit("Le conteneur n'est pas prêt après 60 s, abandon.")

        # 3. publier
        media_id = call("POST", f"{user}/media_publish", {
            "creation_id": container,
            "access_token": token,
        })["id"]
        print(f"Publié ✅ (media id {media_id})")

    log.append({"id": post["id"], "date": today, "media_id": media_id})
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
