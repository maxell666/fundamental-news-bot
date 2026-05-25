import os
import requests
import json
from pathlib import Path

from sources import fetch_reuters, fetch_newsapi
from filter import is_relevant
from scoring import compute_score
from translate import translate_text, debug_deepl_usage, has_deepl_key
from mapping import get_market_impact, priority_label


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = Path("state.json")
MIN_SCORE_SEND = int(os.environ.get("MIN_SCORE_SEND", "5"))
MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "60"))
USE_NEWSAPI = os.environ.get("USE_NEWSAPI", "0") == "1"


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )

    print("Telegram status code:", response.status_code)
    print("Telegram response:", response.text)
    response.raise_for_status()


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


def should_send(text, score):
    return score >= MIN_SCORE_SEND and is_relevant(text)


def main():
    print("=== FUNDAMENTAL NEWS BOT ===")

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

    # Score d’abord, puis tri par importance décroissante
    ranked = []

    for n in unique_news:
        text = f"{n.get('title', '')} {n.get('desc', '')}".lower()
        score = compute_score(text)
        ranked.append((score, n, text))

    ranked.sort(key=lambda x: x[0], reverse=True)

    sent_count = 0

    for score, n, text in ranked[:MAX_ARTICLES_PER_RUN]:
        already_seen = n["url"] in state["seen"]
        status = "SEND" if should_send(text, score) else "IGNORE"

        impacts, assets, bias, category = get_market_impact(text)

        if status == "SEND" and not already_seen:
            title_fr = get_cached_translation(n["title"], state)
        else:
            title_fr = n["title"]

        print("\n------------------------------")
        print(f"Status : {status}")
        print(f"Score  : {score}")
        print(f"Source : {n['source']}")
        print(f"Déjà vu: {already_seen}")
        print(f"Titre  : {title_fr}")

        if status == "SEND" and not already_seen:
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
