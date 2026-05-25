def compute_score(text):
    text = (text or "").lower()
    score = 0

    # Géopolitique tradable
    if any(k in text for k in ["iran", "israel", "ukraine", "russia", "china", "taiwan"]):
        score += 1
    if any(k in text for k in ["war", "conflict", "escalation"]):
        score += 3
    if "attack" in text:
        score += 2
    if "missile" in text or "drone" in text:
        score += 3
    if "military" in text:
        score += 2
    if "sanctions" in text:
        score += 3
    if "nuclear" in text:
        score += 3

    # Énergie / supply shock
    if any(k in text for k in ["oil", "crude", "brent", "wti"]):
        score += 3
    if "gas" in text or "lng" in text:
        score += 2
    if "strait" in text:
        score += 3
    if "hormuz" in text:
        score += 5
    if "red sea" in text or "suez" in text:
        score += 4
    if "opec" in text:
        score += 4

    # Macro / banques centrales
    if "inflation" in text:
        score += 2
    if any(k in text for k in ["cpi", "ppi", "pce"]):
        score += 4
    if "interest rate" in text or "rates" in text:
        score += 3
    if "rate hike" in text or "rate cut" in text:
        score += 4
    if any(k in text for k in ["fed", "fomc", "powell", "federal reserve"]):
        score += 4
    if any(k in text for k in ["ecb", "lagarde", "european central bank"]):
        score += 4
    if any(k in text for k in ["boe", "bailey", "bank of england"]):
        score += 4
    if "central bank" in text:
        score += 3
    if any(k in text for k in ["nonfarm payrolls", "nfp", "jobs report"]):
        score += 4

    # Marchés
    if any(k in text for k in ["dollar", "treasury", "yields", "bond yields", "gold"]):
        score += 2
    if any(k in text for k in ["stocks", "wall street", "nasdaq", "s&p"]):
        score += 2

    return score
