"""Collecte RSS orientée marchés, datée et observable, sans clé supplémentaire."""
import calendar
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests

REUTERS_AGGREGATE_LABEL = "Reuters via Google News"
REUTERS_QUERY = ('site:reuters.com (markets OR business OR economy OR stocks OR oil OR gold '
                 'OR "Federal Reserve" OR tariffs OR sanctions OR earnings) when:1d')
REUTERS_AGGREGATE_URL = "https://news.google.com/rss/search?" + urlencode({
    "q": REUTERS_QUERY, "hl": "en-US", "gl": "US", "ceid": "US:en",
})
# Liens de flux publiés par Investing sur sa page /webmaster-tools/rss.
# Reuters est agrégé par Google News, pas un flux officiel Reuters.
RSS_SOURCES = [
    (REUTERS_AGGREGATE_LABEL, REUTERS_AGGREGATE_URL),
    ("InvestingLive News", "https://investinglive.com/feed/news/"),
    ("InvestingLive Central Banks", "https://investinglive.com/feed/centralbank/"),
    ("Investing.com Stock Markets", "https://www.investing.com/rss/news_25.rss"),
    ("Investing.com Commodities", "https://www.investing.com/rss/news_11.rss"),
    ("Investing.com Economy", "https://www.investing.com/rss/news_14.rss"),
    ("Investing.com Earnings", "https://www.investing.com/rss/news_1062.rss"),
    ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("The Guardian Business", "https://www.theguardian.com/business/rss"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
]
REQUEST_TIMEOUT = (5, 15)
MAX_FEED_BYTES = 2_000_000
try:
    MAX_ITEMS_PER_SOURCE = max(1, min(200, int(os.environ.get("MAX_ITEMS_PER_SOURCE", "50"))))
except ValueError:
    MAX_ITEMS_PER_SOURCE = 50
MAX_FEED_ITEMS = MAX_ITEMS_PER_SOURCE
RSS_HEADERS = {
    "User-Agent": "fundamental-news-bot/3.0 (RSS reader; https://github.com/maxell666/fundamental-news-bot)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
}
TRACKING_PARAMETERS = {"fbclid", "gclid", "oc", "at_medium", "at_campaign"}


class SourceCollectionError(RuntimeError):
    """Aucune source n'a fourni d'article exploitable ; diagnostics conservés."""
    def __init__(self, diagnostics):
        super().__init__("Aucune source RSS n'a fourni d'article exploitable")
        self.diagnostics = diagnostics


def canonical_url(url):
    """Clé de dédoublonnage ; le lien original reste disponible dans url."""
    if not isinstance(url, str):
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return ""
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))


def canonicalize_url(url):
    """Nom explicite partagé avec le dédoublonnage de l'historique du bot."""
    return canonical_url(url)


def _published_at(entry):
    # Ne pas remplacer une publication ancienne par la date d'une retouche.
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        date = datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None
    return date.isoformat().replace("+00:00", "Z")


def _normalize_iso_date(value):
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            return None
    except ValueError:
        return None
    return date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_reuters_entry(entry):
    original = entry.get("source") or {}
    if not isinstance(original, dict):
        return False
    publisher = str(original.get("title", "")).strip().lower()
    original_url = original.get("href") or original.get("url") or ""
    try:
        host = (urlsplit(original_url).hostname or "").lower()
    except (ValueError, TypeError):
        return False
    return publisher in ("reuters", "reuters.com") and host in ("reuters.com", "www.reuters.com")


def _read_feed(url):
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=RSS_HEADERS, stream=True)
    try:
        if response.status_code != 200:
            return None, "HTTP " + str(response.status_code)
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_FEED_BYTES:
                return None, "Flux trop volumineux"
            chunks.append(chunk)
        return b"".join(chunks), None
    finally:
        response.close()


def _fetch_rss(source_name, url):
    """Retourne (articles, santé), y compris pour une réponse 200 vide/invalide."""
    health = {
        "source": source_name, "url": url, "status": "error", "article_count": 0,
        "dated_count": 0, "undated_count": 0, "newest_at": None, "detail": "",
        "primary": not source_name.startswith("BBC "),
        "focus": "general" if source_name.startswith("BBC ") else "markets",
    }
    try:
        body, problem = _read_feed(url)
        if problem:
            health["detail"] = problem
            return [], health
        feed = feedparser.parse(body)
        if not feed.get("version"):
            health["detail"] = "La réponse n'est pas un flux RSS/Atom"
            return [], health
        articles, excluded_publishers = [], 0
        for entry in feed.get("entries", [])[:MAX_FEED_ITEMS]:
            if source_name == REUTERS_AGGREGATE_LABEL and not _is_reuters_entry(entry):
                excluded_publishers += 1
                continue
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            canonical = canonical_url(link)
            if not title or not canonical:
                continue
            item = {
                "title": title[:1000], "desc": (entry.get("summary") or "")[:4000],
                "url": link, "canonical_url": canonical, "source": source_name,
                "published_at": _published_at(entry),
            }
            if source_name == REUTERS_AGGREGATE_LABEL:
                item["original_source"] = "Reuters"
                item["source_kind"] = "aggregated"
            articles.append(item)
        dates = [item["published_at"] for item in articles if item["published_at"]]
        health.update({
            "status": "warning" if feed.get("bozo") and articles else "ok" if articles else "empty",
            "article_count": len(articles), "dated_count": len(dates),
            "undated_count": len(articles) - len(dates), "newest_at": max(dates) if dates else None,
        })
        if health["status"] == "warning":
            health["detail"] = "XML imparfait, entrées RSS exploitables"
        if not articles:
            health["detail"] = "Aucun article exploitable"
        if excluded_publishers:
            health["excluded_publishers"] = excluded_publishers
        return articles, health
    except requests.RequestException:
        health["detail"] = "Échec réseau lors de la collecte"
    except Exception as exc:
        # Jamais de réponse brute ni d'URL issue d'une exception dans les logs.
        health["detail"] = "Erreur de lecture du flux : " + type(exc).__name__
    return [], health


def collect_news(source_specs=None):
    """Collecte bornée ; une panne partielle n'efface pas les autres fournisseurs."""
    specs = list(RSS_SOURCES if source_specs is None else source_specs)
    if not specs:
        raise SourceCollectionError([])
    with ThreadPoolExecutor(max_workers=min(6, len(specs))) as executor:
        results = list(executor.map(lambda spec: _fetch_rss(*spec), specs))
    diagnostics = [health for _, health in results]
    unique = {}
    for articles, _ in results:
        for item in articles:
            key = item["canonical_url"]
            existing = unique.get(key)
            if existing is None:
                unique[key] = item
            else:
                if len(item["desc"]) > len(existing["desc"]):
                    existing["desc"] = item["desc"]
                if not existing.get("published_at"):
                    existing["published_at"] = item.get("published_at")
    if not unique:
        raise SourceCollectionError(diagnostics)
    return list(unique.values()), diagnostics


def fetch_rss_news():
    """Compatibilité : l'ancien appel ne renvoyait que les articles."""
    news, diagnostics = collect_news()
    for health in diagnostics:
        print("RSS source :", health["source"], "|", health["status"],
              "| articles =", health["article_count"], "|", health["detail"])
    return news


def fetch_reuters():
    """Ancien nom conservé pour compatibilité ; utiliser collect_news désormais."""
    return fetch_rss_news()


def fetch_newsapi(api_key=None):
    api_key = api_key or os.environ.get("NEWSAPI_KEY", "")
    if not api_key:
        print("NewsAPI: aucune clé API trouvée")
        return []
    params = {
        "q": "(iran OR israel OR ukraine OR russia OR china OR taiwan OR oil OR sanctions OR inflation OR fed OR ecb OR cpi OR pce OR opec OR hormuz)",
        "language": "en", "sortBy": "publishedAt", "pageSize": 50,
    }
    try:
        response = requests.get("https://newsapi.org/v2/everything", params=params,
                                headers={"X-Api-Key": api_key}, timeout=REQUEST_TIMEOUT,
                                allow_redirects=False)
        if response.status_code != 200:
            print("NewsAPI: collecte refusée (HTTP", response.status_code, ")")
            return []
        data = response.json()
        if not isinstance(data, dict) or data.get("status") != "ok":
            print("NewsAPI: réponse non confirmée")
            return []
    except (requests.RequestException, ValueError):
        print("NewsAPI: échec de collecte, détails masqués")
        return []
    news = []
    for article in data.get("articles", [])[:100]:
        if not isinstance(article, dict):
            continue
        link = article.get("url") or ""
        if not article.get("title") or not canonical_url(link):
            continue
        news.append({
            "title": article["title"], "desc": article.get("description") or "",
            "url": link, "canonical_url": canonical_url(link),
            "source": (article.get("source") or {}).get("name", "NewsAPI"),
            "published_at": _normalize_iso_date(article.get("publishedAt")),
        })
    return news
