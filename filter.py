KEYWORDS = [
    "iran", "war", "attack", "oil", "military",
    "sanctions", "conflict", "missile",
    "inflation", "interest rate", "fed", "ecb"
]


def is_relevant(text):
    text = text.lower()

    for k in KEYWORDS:
        if k in text:
            return True

    return False
