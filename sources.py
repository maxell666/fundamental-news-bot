import os
import requests
import feedparser


RSS_SOURCES = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC Politics", "https://feeds.bbci.co.uk/news/politics/rss.xml"),
]


def _fetch_rss(source_name, url):
    feed = feedparser.parse(url)
    news = []

    for entry in feed.entries:
        news.append({
            "title": getattr(entry, "title", "") or "",
            "desc": getattr(entry, "summary", "") or "",
            "url": getattr(entry, "link", "") or "",
            "source": source_name,
        })

    return news


def fetch_rss_news():
    news = []

    for source_name, url in RSS_SOURCES:
        try:
            news.extend(_fetch_rss(source_name, url))
        except Exception as e:
            print(f"RSS error {source_name}: {e}")

    # dédoublonnage par URL
    seen = set()
    unique = []

    for item in news:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(item)

    return unique


# Compatibilité avec l’ancien bot.py : la fonction s’appelait fetch_reuters,
# mais elle lisait en réalité le flux BBC.
def fetch_reuters():
    return fetch_rss_news()


def fetch_newsapi(api_key=None):
    api_key = api_key or os.environ.get("NEWSAPI_KEY", "")

    if not api_key:
        print("NewsAPI: aucune clé API trouvée")
        return []

    url = (
        "https://newsapi.org/v2/everything?"
        "q=(iran OR israel OR ukraine OR russia OR china OR taiwan OR war OR oil OR sanctions OR inflation OR fed OR ecb OR cpi OR pce OR opec OR hormuz)&"
        "language=en&"
        "sortBy=publishedAt&"
        "pageSize=50&"
        f"apiKey={api_key}"
    )

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print("NewsAPI error:", e)
        return []

    news = []

    for article in data.get("articles", []):
        news.append({
            "title": article.get("title") or "",
            "desc": article.get("description") or "",
            "url": article.get("url") or "",
            "source": article.get("source", {}).get("name", "Unknown"),
        })

    return news
