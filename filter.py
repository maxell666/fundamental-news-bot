"""Filtre de pertinence pour éviter les faux positifs.

Objectif : envoyer uniquement les news utiles pour le trading macro / géopolitique / énergie,
pas les faits divers ni les récits humains qui contiennent des mots forts comme
"attack", "missile" ou "Hormuz".
"""

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

# Bruit clair : faits divers, people, sport, justice locale, récits humains.
EXCLUDE_KEYWORDS = [
    "celebrity", "footballer", "singer", "movie", "film", "rehab",
    "murder", "crime", "trial", "court", "arrest", "jailed", "prison",
    "election", "redistricting", "governor race", "midterms",
]

# Faux positifs fréquents : ils doivent être bloqués sauf vrai contexte marché.
HUMAN_INTEREST_NOISE = [
    "shark attack", "shark", "crocodile", "bear attack", "animal attack",
    "stabbing", "shooting victim", "murdered", "killed by", "death of",
    "i survived", "i survived a", "my friend", "my husband", "my wife",
    "survivor", "survived", "tells how", "tells the story", "family says",
    "tourist", "swimmer", "beach", "coast", "off the coast",
]

# Contexte réellement tradable / marchés. Si un article a des mots de bruit,
# il doit contenir au moins un de ces éléments pour être autorisé.
MARKET_HARD_CONTEXT = [
    # Marchés / prix / actifs
    "oil prices", "oil price", "crude", "brent", "wti", "gold", "dollar",
    "stocks", "stock market", "wall street", "nasdaq", "s&p", "treasury",
    "bond yields", "yields", "market", "markets", "investors", "traders",

    # Supply shock / commerce mondial
    "tanker", "oil tanker", "vessel", "ship", "shipping", "cargo",
    "trade route", "supply", "exports", "imports", "pipeline", "lng",
    "blocked", "closed", "closure", "disruption", "disrupted",
    "red sea", "suez", "opec",

    # Politique monétaire / macro
    "fed", "fomc", "federal reserve", "powell", "ecb", "lagarde",
    "boe", "bailey", "bank of england", "central bank", "inflation",
    "cpi", "ppi", "pce", "nfp", "jobs report", "interest rate",
    "rate cut", "rate hike", "rates",

    # Géopolitique tradable concrète
    "sanctions", "missile attack on", "drone attack on", "air strike",
    "military operation", "navy", "us navy", "iran", "israel", "russia",
    "ukraine", "china", "taiwan", "houthi", "nuclear", "escalation",
]

MARKET_CONTEXT = [
    "oil", "crude", "brent", "wti", "gas", "opec", "hormuz", "strait",
    "fed", "fomc", "ecb", "boe", "inflation", "cpi", "ppi", "pce",
    "rates", "interest rate", "rate cut", "rate hike", "yields",
    "dollar", "euro", "pound", "gold", "stocks", "wall street",
    "nasdaq", "s&p", "treasury", "sanctions", "missile", "drone",
    "war", "military", "conflict", "nuclear", "escalation",
]

CRITICAL_PHRASES = [
    "fomc", "fed decision", "federal reserve", "ecb decision",
    "bank of england", "interest rate decision", "rate cut", "rate hike",
    "cpi", "pce", "nonfarm payrolls", "jobs report", "opec",
    "oil prices", "oil price", "sanctions", "strait of hormuz",
    "missile attack on", "drone attack on", "oil tanker", "shipping route",
]


def _contains_any(text, words):
    return any(k in text for k in words)


def is_noise_story(text):
    """True si l'article ressemble à un fait divers / témoignage non tradable."""
    text = (text or "").lower()

    has_noise = _contains_any(text, HUMAN_INTEREST_NOISE) or _contains_any(text, EXCLUDE_KEYWORDS)
    if not has_noise:
        return False

    has_hard_market_context = _contains_any(text, MARKET_HARD_CONTEXT)

    # Exception : si le bruit est présent mais qu'il y a un vrai élément marché,
    # on laisse passer. Exemple : "oil tanker attacked in Strait of Hormuz".
    if has_hard_market_context:
        return False

    return True


def is_relevant(text):
    text = (text or "").lower()

    # 1) Blocage prioritaire des faits divers / récits humains.
    # Exemple bloqué : "Man killed in shark attack..."
    # Exemple bloqué : "I survived a missile strike in the Strait of Hormuz..."
    if is_noise_story(text):
        return False

    # 2) Phrases très tradables : gardées.
    if _contains_any(text, CRITICAL_PHRASES):
        return True

    # 3) Si blacklist classique sans contexte marché, on bloque.
    has_market_context = _contains_any(text, MARKET_CONTEXT)
    if not has_market_context and _contains_any(text, EXCLUDE_KEYWORDS):
        return False

    # 4) Whitelist générale.
    return _contains_any(text, KEYWORDS)
