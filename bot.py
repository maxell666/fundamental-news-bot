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

    for n in reuters_news[:15]:
        text = (n["title"] + " " + n["desc"]).lower()

        score = compute_score(text)

        # 🔥 condition PRO
        if score >= 4 and is_relevant(text):
            print(f"[SEND] ({score}) {n['title']}")
        else:
            print(f"[IGNORE] ({score}) {n['title']}")
            
    # 🔹 NewsAPI
    print("\n--- NewsAPI ---")
    newsapi_news = fetch_newsapi(NEWSAPI_KEY)

    for n in newsapi_news[:5]:
        print(f"[NewsAPI] {n['title']}")


if __name__ == "__main__":
    main()
