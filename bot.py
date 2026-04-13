from sources import fetch_reuters, fetch_newsapi

# 🔑 A REMPLACER plus tard
NEWSAPI_KEY = "PUT_YOUR_KEY_HERE"


def main():
    print("=== TEST NEWS BOT ===")

    # 🔹 Reuters
    print("\n--- Reuters ---")
    reuters_news = fetch_reuters()

    for n in reuters_news[:5]:  # on limite à 5
        print(f"[Reuters] {n['title']}")

    # 🔹 NewsAPI
    print("\n--- NewsAPI ---")
    newsapi_news = fetch_newsapi(NEWSAPI_KEY)

    for n in newsapi_news[:5]:
        print(f"[NewsAPI] {n['title']}")


if __name__ == "__main__":
    main()
