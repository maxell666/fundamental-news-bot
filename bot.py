from sources import fetch_reuters, fetch_newsapi
from filter import is_relevant

# 🔑 A REMPLACER plus tard
NEWSAPI_KEY = "PUT_YOUR_KEY_HERE"


def main():
    print("=== TEST NEWS BOT ===")

    # 🔹 Reuters
    print("\n--- Reuters ---")
    reuters_news = fetch_reuters()

    for n in reuters_news[:10]:
        text = n["title"] + " " + n["desc"]

        if is_relevant(text):
            print(f"[KEEP] {n['title']}")
        else:
            print(f"[SKIP] {n['title']}")

    # 🔹 NewsAPI
    print("\n--- NewsAPI ---")
    newsapi_news = fetch_newsapi(NEWSAPI_KEY)

    for n in newsapi_news[:5]:
        print(f"[NewsAPI] {n['title']}")


if __name__ == "__main__":
    main()
