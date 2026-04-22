def get_market_impact(text):
    text = text.lower()

    impacts = []
    assets = []
    bias = "Neutre"
    category = "FONDAMENTAL"

    # GEO / guerre / Iran / attaques / missiles
    if any(k in text for k in ["iran", "war", "attack", "missile", "conflict", "military", "sanctions"]):
        category = "GEO"
        bias = "Risk-off"

        impacts += [
            "• Or : haussier",
            "• Indices US : prudence",
            "• Volatilité : en hausse"
        ]

        assets += ["XAUUSD", "US30", "NQ", "SP500"]

    # Energie / pétrole / Hormuz / OPEC
    if any(k in text for k in ["oil", "hormuz", "strait", "opec", "fuel"]):
        category = "ENERGY"
        bias = "Risk-off"

        impacts += [
            "• Pétrole : haussier",
            "• Volatilité énergie : en hausse",
            "• Or : soutien possible"
        ]

        assets += ["XAUUSD", "US30", "NQ", "SP500"]

    # Fed / inflation / CPI / taux
    if any(k in text for k in ["fed", "interest rate", "inflation", "cpi", "rate cut", "rate hike", "central bank"]):
        if category == "FONDAMENTAL":
            category = "MACRO"

        impacts += [
            "• USD : volatilité possible",
            "• Indices US : réaction probable",
            "• Or : sensible aux taux"
        ]

        assets += ["EURUSD", "GBPUSD", "XAUUSD", "US30", "NQ", "SP500"]

    # ECB / Europe
    if any(k in text for k in ["ecb", "european central bank"]):
        if category == "FONDAMENTAL":
            category = "MACRO"

        impacts += [
            "• EUR : volatilité possible",
            "• Indices européens : réaction probable"
        ]

        assets += ["EURUSD", "GER40"]

    if not impacts:
        impacts = ["• Impact à confirmer"]

    # supprime doublons en gardant l'ordre
    impacts = list(dict.fromkeys(impacts))
    assets = list(dict.fromkeys(assets))

    return impacts, assets, bias, category
