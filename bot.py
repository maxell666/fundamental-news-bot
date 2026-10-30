import argparse
import os
import requests
import json
import re
import sys
from html import escape
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sources import SourceCollectionError, collect_news, fetch_newsapi
from filter import FILTER_VERSION, assess_news
from translate import translate_text, debug_deepl_usage, has_deepl_key
from mapping import get_market_impact, priority_label
from news_pipeline import evaluate_news, parse_publication, rank_eligible, summarize, write_audit
from portfolio import assess_portfolio, TRACKED_ASSETS


BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

STATE_FILE = Path("state.json")
MIN_SCORE_SEND = int(os.environ.get("MIN_SCORE_SEND", "5"))
MAX_ARTICLES_PER_RUN = int(os.environ.get("MAX_ARTICLES_PER_RUN", "10"))
USE_NEWSAPI = os.environ.get("USE_NEWSAPI", "0") == "1"
MAX_NEWS_AGE_HOURS = float(os.environ.get("MAX_NEWS_AGE_HOURS", "24"))
ALLOW_UNDATED_NEWS = os.environ.get("ALLOW_UNDATED_NEWS", "0") == "1"
AUDIT_DIR = os.environ.get("NEWS_AUDIT_DIR", "audit")


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


def send_telegram(message, *, parse_mode=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    if parse_mode not in (None, "HTML"):
        raise ValueError("Format Telegram non autorisé")
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }
    if parse_mode is not None:
        data["parse_mode"] = parse_mode

    try:
        response = requests.post(
            url,
            data=data,
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
        "seen_titles": {},
        "seen_events": {},
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

    if not isinstance(state.get("seen_titles"), dict):
        state["seen_titles"] = {}
    if not isinstance(state.get("seen_events"), dict):
        state["seen_events"] = {}

    return state


def load_state():
    if not STATE_FILE.exists():
        return default_state()

    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except (ValueError, OSError):
        raise RuntimeError("Historique illisible : lancement interrompu pour éviter des doublons") from None

    return ensure_state(state)


def save_state(state):
    state = ensure_state(state)

    temporary = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    temporary.replace(STATE_FILE)


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
        "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDCHF": "USD/CHF",
        "GER30": "GER30", "GER40": "GER30", "SPX500": "SP500",
        "SP500": "SP500", "NAS100": "NAS100", "US30": "US30",
    }
    return names.get(a, a)


def build_message(n, title_fr, score, impacts, assets, bias, category):
    impact_text = "\n".join(escape(str(line)) for line in impacts)
    categories = {
        "MACRO": "MACRO", "FISCAL": "POLITIQUE BUDGÉTAIRE",
        "TRADE": "COMMERCE", "EQUITIES": "ENTREPRISES",
        "ENERGY": "ÉNERGIE", "GEO": "GÉOPOLITIQUE", "MARKET": "MARCHÉS",
    }
    publication = parse_publication(n.get("published_at"))
    publication_line = (
        "🕒 Publication : " + publication.astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M")
        + " (Paris)\n"
    ) if publication else ""

    return (
        f"📣 <b>{categories.get(category, 'ACTUALITÉ')}</b>\n\n"
        f"<b>{escape(str(title_fr))}</b>\n\n"
        f"🎯 <b>Lecture pour tes marchés</b>\n{impact_text}\n\n"
        f"{publication_line}"
        f"📰 {escape(str(n['source']))}\n"
        f'🔗 <a href="{escape(str(n["url"]), quote=True)}">Lire l’article</a>'
    )


def should_send(title, score, description=""):
    assessment = assess_news(title, description)
    return (score >= MIN_SCORE_SEND and assessment.relevant
            and assess_portfolio(title, description, category=assessment.category).relevant)


def main(dry_run=None, replay_path=None):
    dry_run = os.environ.get("NEWS_DRY_RUN", "0") == "1" if dry_run is None else dry_run
    use_newsapi = USE_NEWSAPI and not dry_run
    if replay_path and not dry_run:
        raise RuntimeError("Un rejeu de fichier exige le mode --dry-run")
    if MAX_NEWS_AGE_HOURS <= 0 or MAX_ARTICLES_PER_RUN < 1:
        raise RuntimeError("Les limites de fraîcheur et d'envoi doivent être positives")
    print("=== FUNDAMENTAL NEWS BOT ===")
    print("Version du filtre :", FILTER_VERSION)
    print("Mode :", "AUDIT SANS ENVOI" if dry_run else "ALERTES")
    if not dry_run:
        verify_telegram_token()
        if not CHAT_ID:
            raise RuntimeError("Destinataire Telegram absent de la configuration")
    state = load_state()
    now = datetime.now(timezone.utc)
    state["seen_titles"] = {
        key: timestamp for key, timestamp in state.get("seen_titles", {}).items()
        if (date := parse_publication(timestamp)) is not None
        and timedelta(0) <= now - date <= timedelta(hours=24)
    }
    state["seen_events"] = {
        key: event for key, event in state.get("seen_events", {}).items()
        if isinstance(event, dict) and (date := parse_publication(event.get("sent_at"))) is not None
        and timedelta(0) <= now - date <= timedelta(hours=24)
    }
    print("State chargé | seen =", len(state["seen"]), "| translations =", len(state["translations"]))
    rows, health = [], []
    failure = None
    try:
        if replay_path:
            snapshot = json.loads(Path(replay_path).read_text(encoding="utf-8"))
            all_news = snapshot["articles"]
            health = snapshot.get("sources", [])
            if not isinstance(all_news, list) or not isinstance(health, list):
                raise RuntimeError("Format du relevé de sources invalide")
        else:
            try:
                all_news, health = collect_news()
            except SourceCollectionError as exc:
                health = exc.diagnostics
                all_news = []
                if not use_newsapi:
                    raise
            if use_newsapi:
                additional = fetch_newsapi()
                all_news.extend(additional)
                health.append({
                    "source": "NewsAPI", "status": "ok" if additional else "empty",
                    "article_count": len(additional), "primary": True, "focus": "markets",
                })
            if not all_news and health:
                raise RuntimeError("Aucune source n'a fourni d'article exploitable")
        for source in health:
            print("SOURCE_HEALTH", json.dumps(source, ensure_ascii=False))
        print("Articles récupérés :", len(all_news))
        rows = evaluate_news(
            all_news, state, now=now, threshold=MIN_SCORE_SEND,
            max_age_hours=MAX_NEWS_AGE_HOURS, allow_undated=ALLOW_UNDATED_NEWS,
        )
        # Préparer les lectures avant classement : une annonce sans lien
        # argumenté ne consomme pas une place dans le lot d'envoi.
        for row in rows:
            if row["decision"] != "eligible":
                continue
            item = row["article"]
            text = f"{item.get('title', '')} {item.get('desc', '')}"
            impacts, assets, _, category = get_market_impact(
                text, title=item.get("title", ""), category=row["category"]
            )
            allowed = set(row["portfolio_assets"]) & set(TRACKED_ASSETS)
            if not impacts or not assets or not set(assets) <= allowed:
                row.update(decision="no_impact_reading",
                           reason="Lecture absente ou actifs hors du périmètre de trading")
                continue
            row.update(market_impacts=list(impacts), market_assets=list(assets), category=category)
        ranked = rank_eligible(rows, seen_events=state.get("seen_events", {}), now=now)
        chosen = ranked[:MAX_ARTICLES_PER_RUN]
        for row in ranked[MAX_ARTICLES_PER_RUN:]:
            row.update(decision="queued", reason="Limite par passage atteinte ; réexamen au passage suivant")
        for row in chosen:
            if dry_run:
                row["decision"] = "dry_run_selected"
                continue
            row["decision"] = "sending"
            item = row["article"]
            translated = get_cached_translation(item["title"], state)
            try:
                send_telegram(build_message(item, translated, row["score"], row["market_impacts"],
                                            row["market_assets"], None, row["category"]),
                              parse_mode="HTML")
            except Exception:
                row.update(decision="send_failed", reason="Envoi non confirmé ; aucun nouvel essai dans ce lancement")
                raise
            row["decision"] = "sent"
            state["seen"].append(row["canonical_url"])
            state["seen_titles"][row["story_key"]] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if row.get("event_key"):
                state["seen_events"][row["event_key"]] = {
                    "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "value": row["event_value"], "base": row["event_base"],
                }
            save_state(state)
        if not dry_run:
            save_state(state)
        for row in rows:
            print("DECISION", json.dumps({
                key: row[key] for key in ("decision", "score", "category", "source", "published_at", "reason", "title")
            }, ensure_ascii=False))
        print("NEWS_SUMMARY", json.dumps(summarize(rows), ensure_ascii=False))
        print("Alertes envoyées :", sum(row["decision"] == "sent" for row in rows))
        return 0
    except Exception as exc:
        failure = type(exc).__name__
        if isinstance(exc, SourceCollectionError):
            health = exc.diagnostics
            for source in health:
                print("SOURCE_HEALTH", json.dumps(source, ensure_ascii=False))
        raise
    finally:
        write_audit(rows, health, dry_run=dry_run, directory=AUDIT_DIR, error=failure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alertes fondamentales et audit de sélection")
    parser.add_argument("--dry-run", action="store_true", help="Auditer sans Telegram, DeepL ni sauvegarde d'historique")
    parser.add_argument("--replay", help="Classer un relevé de sources JSON, uniquement en dry-run")
    args = parser.parse_args()
    if args.replay and not (args.dry_run or os.environ.get("NEWS_DRY_RUN") == "1"):
        parser.error("--replay exige --dry-run")
    sys.exit(main(dry_run=True if args.dry_run else None, replay_path=args.replay))
