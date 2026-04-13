from sources import fetch_reuters, fetch_newsapi
from filter import is_relevant
from scoring import compute_score

# 🔑 A REMPLACER plus tard
NEWSAPI_KEY = "PUT_YOUR_KEY_HERE"


def main():
    print("=== TEST NEWS BOT ===")

    # 🔹 Reuters
    print("\n--- Reuters ---")
    reuters_news = fetch_reuters()

    for n in reuters_news[:10]:
        text = n["title"] + " " + n["desc"]

        score = compute_score(text)

        if score >= 4:
            print(f"[HIGH] ({score}) {n['title']}")
        elif score >= 2:
            print(f"[MEDIUM] ({score}) {n['title']}")
        else:
            print(f"[LOW] ({score}) {n['title']}")

    # 🔹 NewsAPI
    print("\n--- NewsAPI ---")
    newsapi_news = fetch_newsapi(NEWSAPI_KEY)

    for n in newsapi_news[:5]:
        print(f"[NewsAPI] {n['title']}")


if __name__ == "__main__":
    main()
