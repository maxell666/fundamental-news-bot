def get_market_impact(text):
    text = text.lower()

    impacts = []

    # Géopolitique Iran / guerre / attaques
    if "iran" in text or "war" in text or "attack" in text or "missile" in text:
        impacts.append("• Or : haussier")
        impacts.append("• Indices : prudence")
        impacts.append("• Volatilité : en hausse")

    # Pétrole / énergie
    if "oil" in text or "hormuz" in text or "strait" in text:
        impacts.append("• Pétrole : haussier / volatil")
        impacts.append("• Or : soutien possible")

    # Fed / taux / inflation
    if "fed" in text or "interest rate" in text or "inflation" in text:
        impacts.append("• USD : volatilité possible")
        impacts.append("• Indices US : réaction probable")
        impacts.append("• Or : sensible aux taux")

    # BCE / Europe
    if "ecb" in text or "european central bank" in text:
        impacts.append("• EUR : volatilité possible")
        impacts.append("• Indices européens : réaction probable")

    if not impacts:
        impacts.append("• Impact marché à confirmer")

    # Supprime doublons en gardant l'ordre
    unique_impacts = []
    for item in impacts:
        if item not in unique_impacts:
            unique_impacts.append(item)

    return unique_impacts
