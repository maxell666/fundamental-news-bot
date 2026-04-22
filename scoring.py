def compute_score(text):
    text = text.lower()
    score = 0

    # Iran : seulement si contexte marché / escalade
    if "iran" in text and any(k in text for k in ["oil", "war", "attack", "missile", "sanctions", "strait", "hormuz"]):
        score += 3

    # guerre / escalade
    if "war" in text:
        score += 3
    if "attack" in text:
        score += 2
    if "missile" in text:
        score += 3
    if "military" in text:
        score += 2
    if "sanctions" in text:
        score += 2

    # énergie
    if "oil" in text:
        score += 3
    if "strait" in text:
        score += 3
    if "hormuz" in text:
        score += 4
    if "opec" in text:
        score += 3

    # macro
    if "inflation" in text:
        score += 2
    if "cpi" in text:
        score += 3
    if "interest rate" in text:
        score += 3
    if "rate hike" in text:
        score += 3
    if "rate cut" in text:
        score += 3
    if "fed" in text:
        score += 3
    if "ecb" in text:
        score += 3
    if "central bank" in text:
        score += 2

    return score
