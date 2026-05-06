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

    try:
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

        print("DeepL status:", response.status_code)
        print("DeepL body:", response.text)

        if response.status_code != 200:
            return text

        data = response.json()

        if "translations" not in data:
            print("DeepL: champ 'translations' absent")
            return text

        translated = data["translations"][0]["text"]
        print("DeepL original :", text)
        print("DeepL traduit  :", translated)

        return translated

    except Exception as e:
        print("DeepL exception:", str(e))
        return text

def debug_deepl_usage():
    if not DEEPL_API_KEY:
        print("DeepL usage: aucune clé API trouvée")
        return

    url = "https://api-free.deepl.com/v2/usage"

    response = requests.get(
        url,
        headers={
            "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"
        },
        timeout=20
    )

    print("DeepL usage status:", response.status_code)
    print("DeepL usage body:", response.text)
