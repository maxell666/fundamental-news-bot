KEYWORDS = [
    "iran", "war", "attack", "oil", "military",
    "sanctions", "conflict", "missile",
    "inflation", "interest rate", "fed", "ecb"
]
EXCLUDE_KEYWORDS = [
    "executions",
    "killed",
    "murder",
    "death",
    "crime",
    "stabbing"
]

def is_relevant(text):
    text = text.lower()

    # ❌ blacklist (prioritaire)
    for k in EXCLUDE_KEYWORDS:
        if k in text:
            return False

    # ✅ whitelist
    for k in KEYWORDS:
        if k in text:
            return True

    return False
