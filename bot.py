import os
import requests
import json
import re
from pathlib import Path

from sources import fetch_reuters, fetch_newsapi
from filter import FILTER_VERSION, assess_news
from translate import translate_text, debug_deepl_usage, has_deepl_key
from mapping import get_market_impact, priority_label


BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = Path("state.json")
MIN_SCORE_SEND = int(os.environ.get("MIN_SCORE_SEND", "5"))
MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "60"))
USE_NEWSAPI = os.environ.get("USE_NEWSAPI", "0") == "1"


def verify_telegram_token():
    """Valide le token avec getMe, sans envoyer de message ni journaliser le secret."""
    if not BOT_TOKEN:
        raise RuntimeError("La variable BOT_TOKEN est absente ou vide dans ce run GitHub")
    if BOT_TOKEN.startswith(("ghp_", "github_pat_", "ghs_")):
        raise RuntimeError("BOT_TOKEN contient un jeton GitHub ; un token Telegram de BotFather est requis")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", BOT_TOKEN):
        raise RuntimeError("Format BOT_TOKEN incorrect : attendu chiffres:caractères, sans texte ni espaces internes")
    print("Token Telegram présent, format Telegram valide")
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=20
        )
    except requests.RequestException:
        # Les erreurs requests peuvent inclure l'URL, donc le token.
        raise RuntimeError("Connexion Telegram impossible pendant la validation du token") from None

    if response.status_code != 200:
        raise RuntimeError(
            f"Validation Telegram refusée (HTTP {response.status_code}) : vérifier le token Telegram configuré"
        )
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("Réponse Telegram illisible pendant la validation du token") from None

    identity = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(identity, dict) or payload.get("ok") is not True or identity.get("is_bot") is not True:
        raise RuntimeError("Telegram n'a pas confirmé l'identité du bot")
    username = identity.get("username")
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise RuntimeError("Telegram n'a pas retourné un identifiant de bot valide")

    print("Telegram authentifié :", f"@{username}")
    return identity


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
    except requests.RequestException:
        raise RuntimeError("Envoi Telegram non confirmé : connexion interrompue") from None

    print("Telegram status code:", response.status_code)
    if response.status_code != 200:
        raise RuntimeError(f"Envoi Telegram refusé (HTTP {response.status_code})")
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("Envoi Telegram non confirmé : réponse illisible") from None
    if (not isinstance(payload, dict) or payload.get("ok") is not True
            or not isinstance(payload.get("result"), dict)
            or not isinstance(payload["result"].get("message_id"), int)):
        raise RuntimeError("Envoi Telegram non confirmé par l'API")
    print("Telegram : envoi confirmé")


def default_state():
    return {
        "seen": [],
        "translations": {},
    }


def normalize_translation_key(text):
    """
    Clé stable pour le cache DeepL.
    On normalise seulement les espaces et la casse pour réutiliser la traduction
    si le même titre revient avec une casse légèrement différente.
    """
    return " ".join((text or "").strip().lower().split())


def ensure_state(state):
    base = default_state()

    if not isinstance(state, dict):
        return base

    if not isinstance(state.get("seen"), list):
        state["seen"] = []

    if not isinstance(state.get("translations"), dict):
        state["translations"] = {}

    return state


def load_state():
    if not STATE_FILE.exists():
        return default_state()

    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        return default_state()

    return ensure_state(state)


def save_state(state):
    state = ensure_state(state)

    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_cached_translation(title, state):
    """
    Évite de consommer le quota DeepL inutilement.

    Fonctionnement :
    1) Si le titre existe déjà dans state["translations"], on réutilise la traduction.
    2) Sinon, on appelle DeepL une seule fois.
    3) Si DeepL est disponible, on sauvegarde la traduction dans state["translations"].

    Important :
    - Si aucune clé DeepL n'est configurée, on ne met PAS le titre original en cache.
      Comme ça, si tu ajoutes la clé plus tard, le bot pourra traduire normalement.
    """
    title = (title or "").strip()
    if not title:
        return ""

    key = normalize_translation_key(title)
    cache = state.setdefault("translations", {})

    if key in cache:
        print("DeepL cache HIT:", title)
        return cache[key]

    print("DeepL cache MISS:", title)
    translated = translate_text(title)

    if has_deepl_key():
        cache[key] = translated
        print("DeepL cache SAVE:", title, "=>", translated)
    else:
        print("DeepL cache SKIP: pas de clé API")

    return translated


def format_asset(a):
    names = {
        "USOIL": "US OIL",
        "UKOIL": "UK OIL",
        "SPX500": "SPX500",
        "NAS100": "NAS100",
    }
    return names.get(a, a)


def build_message(n, title_fr, score, impacts, assets, bias, category):
    impact_text = "\n".join(impacts)
    assets_text = "\n".join([f"• {format_asset(a)}" for a in assets]) if assets else "• À confirmer"
    label = priority_label(score)

    return (
        f"🚨 {category} | {label}\n\n"
        f"{title_fr}\n\n"
        f"🎯 Impacts :\n{impact_text}\n\n"
        f"📈 Actifs à surveiller :\n{assets_text}\n\n"
        f"🧭 Bias : {bias}\n"
        f"📊 Score : {score}\n"
        f"📰 Source : {n['source']}\n"
        f"🔗 {n['url']}"
    )


def should_send(title, score, description=""):
    return score >= MIN_SCORE_SEND and assess_news(title, description).relevant


def main():
    print("=== FUNDAMENTAL NEWS BOT ===")
    print("Version du filtre :", FILTER_VERSION)
    print("Fichier du filtre :", Path(assess_news.__code__.co_filename).resolve())

    verify_telegram_token()
    debug_deepl_usage()

    state = load_state()
    print(
        "State chargé | seen =",
        len(state["seen"]),
        "| translations =",
        len(state["translations"]),
    )

    all_news = []

    print("\n--- RSS ---")
    all_news.extend(fetch_reuters())

    if USE_NEWSAPI:
        print("\n--- NewsAPI ---")
        all_news.extend(fetch_newsapi())

    # Dédoublonnage par URL
    unique_news = []
    urls = set()

    for n in all_news:
        url = n.get("url")
        if not url or url in urls:
            continue
        urls.add(url)
        unique_news.append(n)

    print("Articles récupérés :", len(unique_news))

    # Le titre et le résumé restent distincts pour qu'un contexte géopolitique
    # dans le résumé ne transforme pas un témoignage en alerte de marché.
    ranked = []

    for n in unique_news:
        assessment = assess_news(n.get("title", ""), n.get("desc", ""))
        already_seen = n["url"] in state["seen"]
        eligible = assessment.relevant and assessment.score >= MIN_SCORE_SEND
        print(
            "SELECT" if eligible and not already_seen else "IGNORE",
            "| Score :", assessment.score,
            "| Déjà vu :", already_seen,
            "| Motif :", assessment.reason,
            "| Titre :", n.get("title", ""),
        )
        if eligible and not already_seen:
            ranked.append((assessment.score, n, assessment.reason))

    ranked.sort(key=lambda x: x[0], reverse=True)

    sent_count = 0

    # La limite porte sur les nouvelles alertes admissibles, pas sur les anciens
    # articles déjà envoyés ni sur les sujets rejetés.
    for score, n, reason in ranked[:MAX_ARTICLES_PER_RUN]:
        text = f"{n.get('title', '')} {n.get('desc', '')}"
        impacts, assets, bias, category = get_market_impact(text, title=n.get("title", ""))
        title_fr = get_cached_translation(n["title"], state)

        print("\n------------------------------")
        print("Status : SEND")
        print(f"Score  : {score}")
        print(f"Motif  : {reason}")
        print(f"Source : {n['source']}")
        print(f"Titre  : {title_fr}")

        send_telegram(
            build_message(n, title_fr, score, impacts, assets, bias, category)
        )
        state["seen"].append(n["url"])
        sent_count += 1

    save_state(state)
    print(
        "State sauvegardé | seen =",
        len(state["seen"]),
        "| translations =",
        len(state["translations"]),
    )
    print("Alertes envoyées :", sent_count)


if __name__ == "__main__":
    main()
