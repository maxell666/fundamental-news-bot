TRANSLATIONS = {
    "war": "guerre",
    "attack": "attaque",
    "attackers": "assaillants",
    "military": "militaire",
    "missile": "missile",
    "conflict": "conflit",
    "sanctions": "sanctions",
    "oil": "pétrole",
    "inflation": "inflation",
    "interest rate": "taux d'intérêt",
    "central bank": "banque centrale",
    "fed": "fed",
    "ecb": "bce",
    "iran": "iran"
}


def translate_text(text):
    text = text.lower()

    for en, fr in TRANSLATIONS.items():
        text = text.replace(en, fr)

    return text
