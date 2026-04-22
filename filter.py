KEYWORDS = [
    # géopolitique tradable
    "iran", "war", "attack", "missile", "military",
    "sanctions", "conflict", "oil", "strait", "hormuz",

    # macro tradable
    "inflation", "interest rate", "fed", "ecb", "cpi",
    "central bank", "rate cut", "rate hike", "opec"
]

EXCLUDE_KEYWORDS = [
    # faits divers / bruit
    "executions",
    "killed",
    "murder",
    "death",
    "crime",
    "stabbing",
    "rehab",
    "arrest",
    "footballer",
    "singer",
    "celebrity",

    # politique peu tradable seule
    "election",
    "redistricting",
    "governor race",
    "midterms"
]


def is_relevant(text):
    text = text.lower()

    # blacklist prioritaire
    for k in EXCLUDE_KEYWORDS:
        if k in text:
            return False

    # whitelist
    for k in KEYWORDS:
        if k in text:
            return True

    return False
