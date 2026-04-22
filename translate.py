import os
import requests

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")


def translate_text(text):
    if not text:
        return ""

    # Si pas de clé DeepL, on renvoie le texte original
    if not DEEPL_API_KEY:
        print("DeepL: aucune clé API trouvée")
        return text

    url = "https://api-free.deepl.com/v2/translate"

    response = requests.post(
        url,
        headers={
            "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"
        },
        data={
            "text": text,
            "source_lang": "EN",
            "target_lang": "FR"
        },
        timeout=20
    )

    print("DeepL status code:", response.status_code)
    print("DeepL response:", response.text)

    if response.status_code != 200:
        return text

    data = response.json()

    if "translations" not in data:
        return text

    return data["translations"][0]["text"]
