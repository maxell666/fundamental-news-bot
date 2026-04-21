from sources import fetch_reuters, fetch_newsapi
from filter import is_relevant
from scoring import compute_score
from translate import translate_text

# 🔑 A REMPLACER plus tard
NEWSAPI_KEY = "PUT_YOUR_KEY_HERE"
BOT_TOKEN = "8669894437:AAGZqV3WGybOafbE48tPVGxqVsn3TkKNjAg"
CHAT_ID = "6526554977"

import requests
import json

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": message
    })

    print("Telegram status code:", response.status_code)
    print("Telegram response:", response.text)

def load_state():
    with open("state.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open("state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
        
def main():
    print("=== TEST NEWS BOT ===")
    state = load_state()
    print("State chargé :", state)
 
    # 🔹 Reuters
    print("\n--- Reuters ---")
    reuters_news = fetch_reuters()

    for n in reuters_news[:15]:
        text = (n["title"] + " " + n["desc"]).lower()

        score = compute_score(text)

        # 🔥 condition PRO
        
        title_fr = translate_text(n["title"])
        already_seen = n["url"] in state["seen"]
        
        status = "SEND" if n == reuters_news[0] else "IGNORE"

        print("\n------------------------------")
        print(f"Status : {status}")
        print(f"Score  : {score}")
        print(f"Source : {n['source']}")
        print(f"Déjà vu: {already_seen}")
        print(f"Titre  : {title_fr}")

        if status == "SEND" and not already_seen:
            send_telegram(f"🚨 BREAKING – Fondamental\n\n{title_fr}\n\nScore: {score}\nSource: {n['source']}")
            state["seen"].append(n["url"])
            
    # 🔹 NewsAPI
    print("\n--- NewsAPI ---")
    newsapi_news = fetch_newsapi(NEWSAPI_KEY)

    for n in newsapi_news[:5]:
        print(f"[NewsAPI] {n['title']}")

    save_state(state)
    print("State sauvegardé :", state)


if __name__ == "__main__":
    main()
