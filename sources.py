import requests
import feedparser


# 🔹 1. Reuters RSS
def fetch_reuters():
    import feedparser

    url = "http://feeds.bbci.co.uk/news/world/rss.xml"
    feed = feedparser.parse(url)

    news = []

    for entry in feed.entries:
        news.append({
            "title": entry.title,
            "desc": entry.summary,
            "url": entry.link,
            "source": "BBC"
        })

    return news


# 🔹 2. NewsAPI
def fetch_newsapi(api_key):
    url = (
        "https://newsapi.org/v2/everything?"
        "q=iran OR war OR oil OR sanctions&"
        "language=en&"
        "sortBy=publishedAt&"
        f"apiKey={api_key}"
    )

    response = requests.get(url)
    data = response.json()

    news = []

    for article in data.get("articles", []):
        news.append({
            "title": article.get("title"),
            "desc": article.get("description"),
            "url": article.get("url"),
            "source": article.get("source", {}).get("name", "Unknown")
        })

    return news
