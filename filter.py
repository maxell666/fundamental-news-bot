KEYWORDS = [
    # géopolitique tradable
    "iran", "israel", "gaza", "ukraine", "russia", "china", "taiwan",
    "war", "attack", "missile", "drone", "military", "conflict",
    "sanctions", "ceasefire", "nuclear", "escalation",

    # énergie / matières premières
    "oil", "crude", "brent", "wti", "gas", "lng", "pipeline",
    "strait", "hormuz", "red sea", "suez", "opec",

    # macro / banques centrales / marchés
    "inflation", "interest rate", "rates", "bond yields", "yields",
    "fed", "fomc", "powell", "ecb", "lagarde", "boe", "bailey",
    "cpi", "ppi", "pce", "nfp", "jobs report", "central bank",
    "rate cut", "rate hike", "dollar", "euro", "pound", "treasury",
    "stocks", "wall street", "nasdaq", "s&p", "gold"
]

EXCLUDE_KEYWORDS = [
    # bruit peu tradable si aucun contexte marché / macro / géopolitique important
    "celebrity",
    "footballer",
    "singer",
    "movie",
    "film",
    "rehab",
    "stabbing",
    "murder",
    "crime",
    "trial",
    "court",
    "election",
    "redistricting",
    "governor race",
    "midterms",
]

MARKET_CONTEXT = [
    "oil", "crude", "brent", "wti", "gas", "opec", "hormuz", "strait",
    "fed", "fomc", "ecb", "boe", "inflation", "cpi", "ppi", "pce",
    "rates", "interest rate", "rate cut", "rate hike", "yields",
    "dollar", "euro", "pound", "gold", "stocks", "wall street",
    "nasdaq", "s&p", "treasury", "sanctions", "missile", "drone",
    "war", "attack", "military", "conflict", "nuclear", "escalation",
]

CRITICAL_PHRASES = [
    "strait of hormuz",
    "red sea",
    "fomc",
    "fed decision",
    "federal reserve",
    "ecb decision",
    "bank of england",
    "interest rate decision",
    "rate cut",
    "rate hike",
    "cpi",
    "pce",
    "nonfarm payrolls",
    "jobs report",
    "opec",
    "missile attack",
    "drone attack",
    "sanctions",
]


def is_relevant(text):
    text = (text or "").lower()

    # Phrases critiques : jamais bloquées par la blacklist
    if any(k in text for k in CRITICAL_PHRASES):
        return True

    has_market_context = any(k in text for k in MARKET_CONTEXT)

    # La blacklist ne doit bloquer que le bruit sans contexte tradable.
    # Exemple : "murder trial" = ignore ; "missile attack killed..." = garder.
    if not has_market_context:
        for k in EXCLUDE_KEYWORDS:
            if k in text:
                return False

    return any(k in text for k in KEYWORDS)
