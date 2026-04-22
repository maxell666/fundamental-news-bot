def get_market_impact(text):
    text = text.lower()

    impacts = []
    bias = "Neutre"

    # Géopolitique / guerre
    if any(k in text for k in ["iran", "war", "attack", "missile", "conflict"]):
        impacts += [
            "• XAUUSD ↑",
            "• Indices (US30/SPX) ↓",
            "• Volatilité ↑"
        ]
        bias = "Risk-off"

    # Pétrole
    if any(k in text for k in ["oil", "hormuz", "strait", "opec"]):
        impacts += [
            "• Pétrole ↑ / volatil",
            "• XAUUSD soutien"
        ]

    # Fed / inflation / taux
    if any(k in text for k in ["fed", "interest rate", "inflation", "cpi"]):
        impacts += [
            "• USD volatil",
            "• Indices US réaction",
            "• XAUUSD sensible"
        ]

    # ECB
    if any(k in text for k in ["ecb", "european central bank"]):
        impacts += [
            "• EUR volatil",
            "• Indices EU réaction"
        ]

    if not impacts:
        impacts = ["• Impact à confirmer"]

    # remove duplicates
    impacts = list(dict.fromkeys(impacts))

    return impacts, bias
