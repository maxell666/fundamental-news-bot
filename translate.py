import os
import requests

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")


def translate_text(text):
    if not text:
        return ""

    # Si pas de clé DeepL, on renvoie le texte original
    if not DEEPL_API_KEY:
        return text

    url = "https://api-free.deepl.com/v2/translate"

    response = requests.post(
        url,
        data={
            "auth_key": DEEPL_API_KEY,
            "text": text,
            "source_lang": "EN",
            "target_lang": "FR"
        },
        timeout=20
    )

    data = response.json()

    return data["translations"][0]["text"]
