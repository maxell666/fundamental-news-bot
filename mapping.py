def merge_impacts(impacts):
    merged = {}

    for imp in impacts:
        imp = imp.replace("• ", "").strip()
        parts = imp.split(" : ")
        key = parts[0]
        value = parts[1] if len(parts) > 1 else ""

        merged.setdefault(key, [])

        if value and value not in merged[key]:
            merged[key].append(value)

    out = []
    for key, values in merged.items():
        if values:
            out.append(f"• {key} : " + " | ".join(values))
        else:
            out.append(f"• {key}")

    return out


def get_market_impact(text):
    text = (text or "").lower()

    impacts = []
    assets = []
    bias = "Neutre"
    category = "FONDAMENTAL"

    # GEO / guerre / Iran / attaques / missiles
    if any(k in text for k in [
        "iran", "israel", "ukraine", "russia", "china", "taiwan",
        "war", "attack", "missile", "drone", "conflict", "military",
        "sanctions", "nuclear", "escalation"
    ]):
        category = "GEO"
        bias = "Risk-off"

        impacts += [
            "• Or : haussier",
            "• Indices US : prudence",
            "• Volatilité : en hausse"
        ]
        assets += ["XAUUSD", "US30", "NAS100", "SPX500"]

    # Energie / pétrole / Hormuz / OPEC
    if any(k in text for k in [
        "oil", "crude", "brent", "wti", "hormuz", "strait",
        "opec", "fuel", "gas", "lng", "pipeline", "red sea", "suez"
    ]):
        category = "ENERGY"
        bias = "Risk-off"

        impacts += [
            "• Pétrole : haussier",
            "• Volatilité énergie : en hausse",
            "• Or : haussier modéré",
            "• Indices : pression possible si choc énergétique"
        ]
        assets += ["USOIL", "UKOIL", "XAUUSD", "US30", "NAS100", "SPX500"]

    # Fed / inflation / CPI / taux / USD
    if any(k in text for k in [
        "fed", "fomc", "powell", "federal reserve", "interest rate",
        "rates", "inflation", "cpi", "ppi", "pce", "rate cut",
        "rate hike", "central bank", "treasury", "yields", "dollar",
        "nonfarm payrolls", "nfp", "jobs report"
    ]):
        if category == "FONDAMENTAL":
            category = "MACRO"

        impacts += [
            "• USD : volatilité en hausse",
            "• Indices US : à surveiller",
            "• Or : très sensible aux taux/rendements"
        ]
        assets += ["DXY", "EURUSD", "GBPUSD", "XAUUSD", "US30", "NAS100", "SPX500"]

    # ECB / Europe
    if any(k in text for k in ["ecb", "lagarde", "european central bank", "eurozone"]):
        if category == "FONDAMENTAL":
            category = "MACRO"

        impacts += [
            "• EUR : volatilité en hausse",
            "• Indices européens : à surveiller"
        ]
        assets += ["EURUSD", "GER40"]

    # BoE / UK
    if any(k in text for k in ["boe", "bailey", "bank of england", "pound", "sterling", "uk inflation"]):
        if category == "FONDAMENTAL":
            category = "MACRO"

        impacts += [
            "• GBP : volatilité en hausse",
            "• GBPUSD : à surveiller"
        ]
        assets += ["GBPUSD"]

    if not impacts:
        impacts = ["• Impact à confirmer"]

    impacts = merge_impacts(impacts)
    assets = list(dict.fromkeys(assets))

    return impacts, assets, bias, category


def priority_label(score):
    if score >= 9:
        return "CRITICAL"
    if score >= 5:
        return "HIGH"
    return "WATCH"
