def compute_score(text):
    text = text.lower()
    score = 0

    # 🔥 Géopolitique forte
    if "iran" in text:
        score += 2
    if "war" in text:
        score += 3
    if "attack" in text:
        score += 2
    if "missile" in text:
        score += 3
    if "military" in text:
        score += 2

    # 🛢️ Energie (très important)
    if "oil" in text:
        score += 3
    if "strait" in text:
        score += 3
    if "hormuz" in text:
        score += 4

    # 💰 Macro
    if "inflation" in text:
        score += 2
    if "interest rate" in text:
        score += 2
    if "fed" in text or "ecb" in text:
        score += 3

    return score
