from filter import assess_news, contains_any


def merge_impacts(impacts):
    return list(dict.fromkeys(impacts))


def _equity_assets(headline):
    # Les tickers identifient d'abord les valeurs effectivement citées.
    groups = (
        (("apple",), ["AAPL", "NAS100", "SPX500", "US30"]),
        (("microsoft",), ["MSFT", "NAS100", "SPX500", "US30"]),
        (("nvidia",), ["NVDA", "NAS100", "SPX500", "US30"]),
        (("alphabet", "google"), ["GOOGL", "NAS100", "SPX500"]),
        (("amazon",), ["AMZN", "NAS100", "SPX500", "US30"]),
        (("meta", "facebook"), ["META", "NAS100", "SPX500"]),
        (("tesla",), ["TSLA", "NAS100", "SPX500"]),
        (("caterpillar",), ["CAT", "US30", "SPX500"]),
        (("jpmorgan", "jp morgan"), ["JPM", "US30", "SPX500"]),
        (("ibm",), ["IBM", "US30", "SPX500"]),
        (("merck",), ["MRK", "US30", "SPX500"]),
        (("boeing",), ["BA", "US30", "SPX500"]),
        (("goldman sachs",), ["GS", "US30", "SPX500"]),
        (("salesforce",), ["CRM", "US30", "SPX500"]),
        (("broadcom",), ["AVGO", "NAS100", "SPX500"]),
        (("amd",), ["AMD", "NAS100", "SPX500"]),
        (("intel",), ["INTC", "NAS100", "SPX500"]),
        (("servicenow", "service now"), ["NOW", "SPX500"]),
        (("fortinet",), ["FTNT", "NAS100", "SPX500"]),
        (("doordash",), ["DASH", "NAS100", "SPX500"]),
        (("instacart",), ["CART"]),
        (("adt",), ["ADT"]),
    )
    assets = []
    for terms, targets in groups:
        if contains_any(headline, terms):
            assets.extend(targets)
    return list(dict.fromkeys(assets)) or ["SPX500"]


def _macro_assets(headline, context):
    groups = (
        (("fed", "fomc", "federal reserve", "powell", "us", "u.s.", "american"),
         ["DXY", "EURUSD", "GBPUSD", "XAUUSD", "US30", "NAS100", "SPX500"]),
        (("ecb", "european central bank", "eurozone", "german", "germany", "euro area"),
         ["EURUSD", "GER40", "XAUUSD"]),
        (("boe", "bank of england", "uk", "britain", "british", "chancellor"),
         ["GBPUSD", "UK100", "XAUUSD"]),
        (("bank of canada", "boc", "canada", "canadian"), ["USDCAD", "XAUUSD"]),
        (("reserve bank of australia", "rba", "australia", "australian"), ["AUDUSD", "XAUUSD"]),
        (("reserve bank of new zealand", "rbnz", "new zealand"), ["NZDUSD", "XAUUSD"]),
        (("bank of japan", "boj", "japan", "japanese"), ["USDJPY", "XAUUSD"]),
        (("swiss national bank", "snb", "switzerland", "swiss"), ["USDCHF", "XAUUSD"]),
    )
    for candidate in (headline, context):
        for terms, assets in groups:
            if contains_any(candidate, terms):
                return assets
    return ["DXY", "XAUUSD", "US30", "NAS100", "SPX500"]


def get_market_impact(text, title=None, category=None):
    context = text or ""
    headline = title if title is not None else context
    if category is None:
        category = assess_news(headline, context).category

    if category == "MACRO":
        return [
            "• Devises et rendements : sensibles au chiffre ou à la décision",
            "• Or et indices : réaction à surveiller selon la surprise de marché",
        ], _macro_assets(headline, context), "À confirmer", category

    if category == "FISCAL":
        return [
            "• Devise et taux du pays : sensibles aux mesures annoncées",
            "• Indices et secteurs concernés : réaction à surveiller",
        ], _macro_assets(headline, context), "À confirmer", category

    if category == "TRADE":
        assets = ["US30", "NAS100", "SPX500", "DXY", "XAUUSD"]
        if contains_any(headline, ("oil", "crude", "gas", "lng", "diesel", "fuel", "gasoline", "petrol")):
            assets += ["USOIL", "UKOIL"]
        return [
            "• Indices et secteurs concernés : sensibles aux mesures commerciales",
            "• USD et or : réaction à confirmer selon la portée des mesures",
        ], assets, "À confirmer", category

    if category == "EQUITIES":
        return [
            "• Valeur concernée : surveiller résultats, perspectives et réaction du cours",
            "• Indices US : effet dépendant du poids de la société",
        ], _equity_assets(headline), "À confirmer", category

    if category == "ENERGY":
        return [
            "• Pétrole : réaction liée à l'offre, la demande et aux stocks",
            "• Indices et devises : sensibles à l'évolution du coût de l'énergie",
        ], ["USOIL", "UKOIL", "XAUUSD", "US30", "NAS100", "SPX500"], "À confirmer", category

    if category == "GEO":
        assets = ["XAUUSD", "US30", "NAS100", "SPX500"]
        if contains_any(headline, ("oil", "gas", "hormuz", "suez", "red sea", "refinery", "pipeline")):
            assets += ["USOIL", "UKOIL"]
        return [
            "• Actifs refuges, indices et volatilité : réaction à surveiller",
            "• Portée de l'événement et réaction effective des marchés à confirmer",
        ], assets, "À confirmer", category

    if category == "MARKET":
        assets = []
        if contains_any(headline, ("gold", "gold prices")):
            assets += ["XAUUSD"]
        if contains_any(headline, ("oil", "crude", "brent", "wti", "natural gas")):
            assets += ["USOIL", "UKOIL"]
        if contains_any(headline, ("dollar", "dxy", "treasury", "treasuries", "yields")):
            assets += ["DXY", "EURUSD", "GBPUSD", "XAUUSD"]
        if contains_any(headline, ("nasdaq",)):
            assets += ["NAS100"]
        if contains_any(headline, ("s&p 500", "s&p500")):
            assets += ["SPX500"]
        if contains_any(headline, ("dow", "dow jones")):
            assets += ["US30"]
        if contains_any(headline, ("wall street", "us stocks", "u.s. stocks", "global stocks", "stock markets")):
            assets += ["US30", "NAS100", "SPX500"]
        if contains_any(headline, ("dax",)):
            assets += ["GER40"]
        return [
            "• Prix : mouvement signalé par la source",
            "• Volatilité et poursuite du mouvement : à surveiller",
        ], list(dict.fromkeys(assets)) or ["US30", "NAS100", "SPX500", "XAUUSD"], "À confirmer", category

    return ["• Impact de marché à confirmer"], [], "À confirmer", "FONDAMENTAL"


def priority_label(score):
    if score >= 9:
        return "CRITICAL"
    if score >= 5:
        return "HIGH"
    return "WATCH"
