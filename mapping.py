"""Lectures causales bornées pour le portefeuille suivi.

Le gate de portefeuille décide de la pertinence ; les règles ci-dessous ne
rajoutent aucun instrument. Les flèches décrivent un mouvement observé ou un
canal conditionnel documenté, jamais une prédiction générale du marché.
"""

import re

from filter import assess_news, contains_any, normalize_text
from portfolio import TRACKED_ASSETS, assess_portfolio


_US_INDICES = ("SP500", "NAS100", "US30")
_INDICES = ("GER30",) + _US_INDICES
_USD_PAIRS = ("EURUSD", "GBPUSD", "USDCHF")
_SPECULATIVE = re.compile(
    r"\b(?:could|might|would|may|expected to|likely to|plans? to|considers?|"
    r"weighs?|urges?|calls? for|bets? on|hopes? for|debates?|discusses?|"
    r"signals?|hints?|sees?|expects?|predicts?|foresees?|considers?|mulls?)\b"
)
_UP = r"(?:rises?|rose|rising|raises?|raised|increases?|increased|jumps?|jumped|surges?|surged|climbs?|climbed|gains?|gained|rall(?:y|ies|ied)|higher|up)"
_DOWN = r"(?:falls?|fell|falling|drops?|dropped|slides?|slid|slumps?|slumped|plunges?|plunged|declines?|declined|loses?|lost|lower|down|sinks?|sank|tumbles?|tumbled)"
_NUMBER = r"([+-]?\d+(?:\.\d+)?)\s*%?"


def merge_impacts(impacts):
    return list(dict.fromkeys(impacts))


def _has(text, pattern):
    return bool(re.search(pattern, text))


def _direction(text):
    """Un verbe opposé dans la même observation interdit une flèche unique."""
    up = _has(text, r"\b" + _UP + r"\b")
    down = _has(text, r"\b" + _DOWN + r"\b")
    return "mixed" if up and down else "up" if up else "down" if down else None


def _surprise_one(text):
    """Consensus d'une même clause, sans comparaison niée ni unités opposées."""
    if _has(text, r"\b(?:not|never|fails? to|failed to|doesn't|didn't|no longer)\b"):
        return None
    if len(_periods(text)) > 1 or ("%" in text and _has(text, r"\b(?:bps?|basis points?)\b")):
        return None
    directions = set()
    if _has(text, r"\b(?:above|higher than|hotter than|stronger than|tops?|beats?|exceeds?|overshoots?)\b.{0,22}\b(?:expectations?|expected|forecasts?|forecast|estimates?|estimate|consensus)\b|\b(?:above|stronger|higher|hotter)[- ]than[- ]expected\b"):
        directions.add("up")
    if _has(text, r"\b(?:below|lower than|cooler than|weaker than|misses?|undershoots?)\b.{0,22}\b(?:expectations?|expected|forecasts?|forecast|estimates?|estimate|consensus)\b|\b(?:below|weaker|lower|cooler)[- ]than[- ]expected\b"):
        directions.add("down")
    # Les unités de chaque côté doivent être identiques. Les signes sont conservés.
    number_unit = r"([+-]?\d+(?:\.\d+)?)\s*(%|bps?|basis points?)?"
    patterns = (
        number_unit + r"\s*(?:vs\.?|versus|against|compared (?:with|to))\s*" + number_unit + r"\s*(?:expected|forecasts?|estimates?|consensus)\b",
        number_unit + r"\s*\((?:vs\.?\s*)?(?:expected|forecast|estimate|consensus)\s*:?\s*" + number_unit + r"\)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            actual, actual_unit, expected, expected_unit = match.groups()
            if (actual_unit or "") != (expected_unit or ""):
                continue
            actual, expected = float(actual), float(expected)
            if actual != expected:
                directions.add("up" if actual > expected else "down")
    return "mixed" if len(directions) > 1 else next(iter(directions), None)


def _periods(text):
    groups = (
        ("annual", r"\b(?:y/y|yoy|year[- ]on[- ]year|annual(?:ly)?)\b"),
        ("monthly", r"\b(?:m/m|mom|month[- ]on[- ]month|monthly)\b"),
        ("quarterly", r"\b(?:q/q|qoq|quarter[- ]on[- ]quarter|quarterly)\b"),
    )
    return {key for key, pattern in groups if _has(text, pattern)}


def _combine_surprises(results):
    directions = {result for result in results if result}
    return "mixed" if "mixed" in directions or len(directions) > 1 else next(iter(directions), None)


_CLAUSE_BREAK = r";|(?<!\d)[.!?](?!\d)|\b(?:but|while|whereas|and|after|as|amid|because|following)\b"
_INFLATION_MARKER = r"\b(?:(?:core|headline|underlying)\s+)?(?:cpi|pce|ppi|inflation|consumer prices|producer prices)\b"
_OTHER_DATA = r"\b(?:gdp|payrolls?|nfp|unemployment|jobless claims|eps|earnings|revenue|retail sales|pmi)\b"
_COUNTRIES = {
    "USD": ("us", "u.s.", "united states", "american"),
    "EUR": ("eurozone", "euro area", "euro zone", "germany", "german", "ecb"),
    "GBP": ("uk", "united kingdom", "britain", "british", "england"),
    "CHF": ("swiss", "switzerland"),
    "FOREIGN": ("canada", "canadian", "australia", "australian", "japan", "japanese", "china", "chinese"),
}
_MONTH = r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b"


def _indicator(text):
    match = re.search(_INFLATION_MARKER, text)
    if not match:
        return None
    indicator = re.sub(r"^(?:core|headline|underlying)\s+", "", match.group())
    return {"consumer prices": "cpi", "producer prices": "ppi"}.get(indicator, indicator)


def _inflation_clauses(text, family, scope, headline_periods, headline_months, summary=False):
    """Aucune surprise du PIB/EPS/autre pays n'est transférée à l'inflation."""
    clauses = []
    spans = []
    for raw in re.split(_CLAUSE_BREAK, text):
        markers = list(re.finditer(_INFLATION_MARKER, raw))
        if not markers:
            continue
        boundaries = [0] + [match.start() for match in markers[1:]] + [len(raw)]
        spans.extend(raw[start:end] for start, end in zip(boundaries, boundaries[1:]))
    for clause in spans:
        marker = re.search(_INFLATION_MARKER, clause)
        if not marker:
            continue
        actual_family = _indicator(clause)
        if family != "inflation" and actual_family not in (family, "inflation"):
            continue
        # Une comparaison d'un autre indicateur après le CPI reste hors de sa clause.
        other = re.search(_OTHER_DATA, clause[marker.end():])
        if other:
            clause = clause[:marker.end() + other.start()]
        country_scopes = {key for key, names in _COUNTRIES.items() if contains_any(clause, names)}
        if country_scopes and country_scopes != {scope}:
            continue
        periods = _periods(clause)
        months = set(re.findall(_MONTH, clause))
        if len(periods) > 1 or len(months) > 1:
            continue
        if headline_periods and periods and headline_periods != periods:
            continue
        if headline_months and months and headline_months != months:
            continue
        if summary and _has(clause, r"\b(?:last month|last year|previous month|previous year|a year ago|last quarter)\b"):
            continue
        clauses.append(clause)
    return clauses


def _inflation_surprise(headline, description, drivers):
    family = _indicator(headline)
    if family is None:
        return None
    scope = next((driver[:3] for driver in drivers if driver in ("USD_DATA", "EUR_DATA", "GBP_DATA", "CHF_DATA")), None)
    if scope is None:
        return None
    # L'appel historique du bot concatène titre et résumé : ne pas relire le titre.
    if description.startswith(headline):
        description = description[len(headline):].lstrip(" .;:-")
    headline_periods = _periods(headline)
    headline_months = set(re.findall(_MONTH, headline))
    if len(headline_periods) > 1 or len(headline_months) > 1:
        return None
    head_clauses = _inflation_clauses(headline, family, scope, set(), set())
    head_result = _combine_surprises(_surprise_one(clause) for clause in head_clauses)
    desc_clauses = _inflation_clauses(description, family, scope, headline_periods, headline_months, summary=True)
    # Un chiffre fiable dans le titre prime. Le résumé ne peut alors qu'identifier
    # une composante opposée de ce même indicateur et de ce même rapport.
    if head_result:
        complementary = [clause for clause in desc_clauses if contains_any(clause, ("core", "headline", "underlying"))]
        return _combine_surprises([head_result] + [_surprise_one(clause) for clause in complementary])
    return _combine_surprises(_surprise_one(clause) for clause in desc_clauses)


def _primary_clause(headline):
    # Les clauses causales ne changent pas l'acteur ou le tenor de l'événement.
    if re.match(r"^(?:after|as|amid|following|while|although|since|during)\b", headline) and "," in headline:
        headline = headline.split(",", 1)[1].strip()
    return re.split(r"\b(?:after|as|amid|while|despite|but|although|following|because|since|during)\b|[;,]", headline, maxsplit=1)[0]


_BANKS = {
    "USD_POLICY": r"\b(?:fed|fomc|federal reserve|powell|warsh)\b",
    "EUR_POLICY": r"\b(?:ecb|european central bank|lagarde)\b",
    "GBP_POLICY": r"\b(?:boe|bank of england|bailey)\b",
    "CHF_POLICY": r"\b(?:snb|swiss national bank|schlegel)\b",
}


def _policy_action(headline, driver):
    primary = _primary_clause(headline)
    actor = re.search(_BANKS[driver], primary)
    if not actor:
        return None
    clause = primary[actor.end():]
    # Même sans virgule, le verbe d'une autre banque n'appartient pas à cet acteur.
    other_actor = re.search("|".join(_BANKS.values()), clause)
    if other_actor:
        clause = clause[:other_actor.start()]
    if (_SPECULATIVE.search(clause)
            or _has(clause, r"\b(?:says?|said|supports?|backs?|recommends?|argues?|believes?|not|fails? to|failed to)\b")):
        return None
    if _has(clause, r"\b(?:holds?|held|keeps?|kept|leaves?|left|maintains?|maintained)\b.{0,40}\b(?:rates?|borrowing costs?)\b|\b(?:rates?|borrowing costs?)\b.{0,25}\b(?:unchanged|on hold|steady)\b"):
        return "hold"
    if _has(clause, r"\b(?:cuts?|cut|lowers?|lowered|reduces?|reduced|slashes?|slashed)\b.{0,30}\b(?:rates?|borrowing costs?)\b|\b(?:announces?|announced|delivers?|delivered)\b.{0,25}\brate cut\b"):
        return "cut"
    if _has(clause, r"\b(?:hikes?|hiked|raises?|raised|increases?|increased)\b.{0,30}\b(?:rates?|borrowing costs?)\b|\b(?:announces?|announced|delivers?|delivered)\b.{0,25}\brate hike\b"):
        return "hike"
    return None


def _yield_move(headline, driver):
    """Tenor, prix/rendement et mouvement viennent de la même clause US."""
    clause = re.split(r"\b(?:and|whereas)\b", _primary_clause(headline), maxsplit=1)[0]
    if _SPECULATIVE.search(clause) or _has(clause, r"\b(?:not|fails? to|failed to)\b"):
        return None
    if driver == "US10Y" and not _has(clause, r"\b(?:us10y|10[- ]year|ten[- ]year)\b"):
        return None
    # US10Y est lui-même une cotation de rendement, sauf prix explicitement nommé.
    price = contains_any(clause, ("price", "prices"))
    yield_quote = contains_any(clause, ("yield", "yields", "rendement", "rendements", "us10y")) and not price
    direction = _direction(clause)
    if direction not in ("up", "down"):
        return direction
    if yield_quote:
        return direction
    if price or contains_any(clause, ("treasury", "treasuries", "us bonds", "u.s. bonds", "government bonds")):
        return {"up": "down", "down": "up"}[direction]
    return None


def _observed_moves(headline):
    primary = _primary_clause(headline)
    # La devise de base CHF doit être inversée pour afficher USD/CHF.
    explicit_chf = (
        (r"\b(?:dollar|usd|greenback)\b(.{0,50}?)\b(?:against|versus|vs\.?)\s+(?:the\s+)?(?:swiss franc|chf)\b", False),
        (r"\b(?:swiss franc|chf)\b(.{0,50}?)\b(?:against|versus|vs\.?)\s+(?:the\s+)?(?:us\s+)?(?:dollar|usd|greenback)\b", True),
    )
    for pattern, invert in explicit_chf:
        match = re.search(pattern, primary)
        if match:
            move = _direction(match.group(1))
            if move in ("up", "down"):
                return {"USDCHF": ({"up": "down", "down": "up"}[move] if invert else move)}
    patterns = (
        ("NAS100", r"\b(?:nasdaq(?: 100| composite)?|nas100)\b"),
        ("SP500", r"\b(?:s&p\s*500|sp500|spx500)\b"),
        ("US30", r"\b(?:dow(?: jones)?|us30)\b"),
        ("GER30", r"\b(?:dax(?: 40| 30)?|ger30|ger40)\b"),
        ("EURUSD", r"\b(?:eur/?usd|euro against (?:the )?(?:us )?dollar)\b"),
        ("GBPUSD", r"\b(?:gbp/?usd|pound against (?:the )?(?:us )?dollar|sterling against (?:the )?dollar)\b"),
        ("USDCHF", r"\b(?:usd/?chf|dollar against (?:the )?swiss franc)\b"),
    )
    if contains_any(headline, ("dollar", "usd", "greenback")):
        patterns += (
            ("EURUSD", r"\beuro\b"),
            ("GBPUSD", r"\b(?:sterling|pound)\b"),
        )
    occurrences = []
    for asset, pattern in patterns:
        occurrences.extend((match.start(), match.end(), asset) for match in re.finditer(pattern, headline))
    occurrences.sort()
    result = {}
    for index, (start, end, asset) in enumerate(occurrences):
        stop = occurrences[index + 1][0] if index + 1 < len(occurrences) else len(headline)
        clause = re.split(r"\b(?:as|after|amid|despite|because|on hopes|following)\b", headline[end:stop], maxsplit=1)[0]
        move = _direction(clause)
        if move in ("up", "down"):
            result[asset] = move
        elif asset in _INDICES:
            # Un extrême de niveau ne donne pas le signe de la séance.
            level = re.search(
                r"\b(?:hits?|reaches?|touches?|hovers?|trades?|near)\b.{0,55}\b(low|high)s?\b",
                clause,
            )
            if level:
                result[asset] = level.group(1)
    # Une expression de marché US englobe uniquement les trois indices US.
    if not result and contains_any(headline, ("wall street", "us stocks", "u.s. stocks", "us stock futures")):
        for match in re.finditer(r"\b(?:wall street|u\.?s\.? stocks|us stock futures)\b", headline):
            clause = re.split(r"\b(?:as|after|amid|because|following)\b", headline[match.end():], maxsplit=1)[0]
            move = _direction(clause)
            if move in ("up", "down"):
                result.update({asset: move for asset in _US_INDICES})
    return result


def get_market_impact(text, title=None, category=None):
    """Retour compatible : impacts français, actifs suivis, biais absent, catégorie."""
    headline = normalize_text(title if title is not None else text)
    description = normalize_text(text if title is not None else "")
    context = " ".join((headline, description))
    if category is None:
        category = assess_news(headline, description).category
    assessment = assess_portfolio(headline, description, category=category)
    if not assessment.relevant:
        return [], [], None, category

    allowed = set(assessment.assets) & set(TRACKED_ASSETS)
    drivers = set(assessment.drivers)
    impacts, used_assets = [], set()

    def add(assets, mechanism):
        selected = [asset for asset in TRACKED_ASSETS if asset in allowed and asset in assets]
        if selected:
            labels = {"EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDCHF": "USD/CHF"}
            impacts.append("• " + " ; ".join(labels.get(asset, asset) for asset in selected) + " : " + mechanism)
            used_assets.update(selected)

    def dollar_channel(tighter, cause):
        direction = "baisse" if tighter else "hausse"
        inverse = "hausse" if tighter else "baisse"
        dollar = "renforce" if tighter else "affaiblit"
        add(("EURUSD", "GBPUSD"), cause + " : " + direction + " possible si le différentiel de taux " + dollar + " le dollar.")
        if "GLOBAL_RISK" in drivers or contains_any(context, ("safe haven", "safe-haven", "risk aversion", "flight to safety")):
            add(("USDCHF",), cause + " ; dollar et franc peuvent tous deux attirer les flux refuges, le sens de la paire dépend de leur force relative.")
        else:
            add(("USDCHF",), cause + " : " + inverse + " possible si le dollar " + ("se renforce" if tighter else "s'affaiblit") + " face au franc.")

    # Un cours observé ne prouve pas un mouvement des six autres instruments.
    observed = _observed_moves(headline) if category == "MARKET" or "OBSERVED_MOVE" in drivers else {}
    observed = {asset: move for asset, move in observed.items() if asset in allowed}
    if observed:
        for move, label in (("up", "hausse"), ("down", "baisse")):
            add(tuple(asset for asset, direction in observed.items() if direction == move), label + " observée dans la dépêche ; cette observation ne prédit pas la prochaine variation.")
        for level, label in (("low", "creux"), ("high", "sommet")):
            add(tuple(asset for asset, value in observed.items() if value == level), "niveau proche d'un " + label + " signalé ; ce niveau ne donne pas la variation de la séance ni la prochaine direction.")
        return impacts, [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category

    if "OBSERVED_MOVE" in drivers:
        dollar_move = _direction(headline) if re.match(r"^dollar\b", headline) else None
        if dollar_move in ("up", "down"):
            stronger = dollar_move == "up"
            add(("EURUSD", "GBPUSD"), "dollar en " + ("hausse" if stronger else "baisse") + " signalé : composante USD orientant ces paires " + ("à la baisse" if stronger else "à la hausse") + " si l'euro et la livre restent stables ; leur variation propre n'est pas donnée.")
            add(("USDCHF",), "dollar en " + ("hausse" if stronger else "baisse") + " signalé : la paire dépend aussi du franc ; un flux refuge vers le CHF peut modifier le sens de USD/CHF.")
        elif contains_any(headline, ("software stocks", "chip stocks", "semiconductor stocks", "tech stocks")):
            add(_US_INDICES, "mouvement du secteur technologique signalé : contribution à l'indice selon le poids de ses composantes, sans établir la variation de l'indice entier.")
        elif contains_any(headline, ("global stocks", "global equities", "world stocks")):
            add(_INDICES, "mouvement des actions mondiales signalé : transmission possible par la prime de risque et les flux internationaux, sans établir ici le cours propre de chaque indice.")
        return impacts, [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category

    if drivers & {"US10Y", "US_RATES"}:
        rate_driver = "US10Y" if "US10Y" in drivers else "US_RATES"
        rate_name = "US10Y" if rate_driver == "US10Y" else "rendements obligataires US"
        move = _yield_move(headline, rate_driver)
        if move == "up":
            add(_INDICES, rate_name + " en hausse : coût d'actualisation accru, pression de valorisation possible, surtout sur NAS100 si ce taux reste élevé.")
        elif move == "down":
            add(_INDICES, "rendements obligataires US en baisse : coût d'actualisation réduit, soutien de valorisation possible ; une crainte de récession peut le contrebalancer.")
        else:
            add(_INDICES, rate_name + " : coût d'actualisation des bénéfices modifié ; le sens du rendement n'est pas établi dans le titre.")
        add(_USD_PAIRS, "un mouvement des rendements US peut venir du taux attendu ou de la prime de terme ; sans comparaison avec les taux européens, britanniques et suisses, aucun sens de change n'est déduit.")
        return impacts, [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category

    policy_drivers = drivers & {"USD_POLICY", "EUR_POLICY", "GBP_POLICY", "CHF_POLICY"}
    if policy_drivers and category not in ("TRADE", "FISCAL"):
        policy_groups = (
            ("USD_POLICY", "Fed", _USD_PAIRS + _INDICES),
            ("EUR_POLICY", "BCE", ("EURUSD", "GER30")),
            ("GBP_POLICY", "BoE", ("GBPUSD",)),
            ("CHF_POLICY", "BNS", ("USDCHF",)),
        )
        for driver, bank, targets in policy_groups:
            if driver not in policy_drivers:
                continue
            action = _policy_action(headline, driver)
            if action in ("hike", "cut"):
                hike = action == "hike"
                cause = bank + (" : hausse du taux directeur" if hike else " : baisse du taux directeur")
                if driver == "USD_POLICY":
                    dollar_channel(hike, cause + ", effet conditionnel à ce qui était déjà intégré dans les cours")
                    add(_INDICES, cause + (" : crédit et actualisation plus coûteux, pression possible sur les valorisations" if hike else " : crédit et actualisation moins coûteux, soutien possible aux valorisations") + " ; l'anticipation de cette décision et la croissance peuvent modifier cet effet.")
                elif driver == "EUR_POLICY":
                    add(("EURUSD",), cause + (" : soutien possible à l'euro" if hike else " : pression possible sur l'euro") + " si le différentiel avec les taux US évolue dans ce sens ; effet déjà anticipé possible.")
                    add(("GER30",), cause + (" : financement et actualisation plus coûteux pour les entreprises du DAX (alias GER30)." if hike else " : financement et actualisation moins coûteux pour les entreprises du DAX (alias GER30).") + " L'effet dépend des anticipations et des perspectives de bénéfices.")
                elif driver == "GBP_POLICY":
                    add(("GBPUSD",), cause + (" : soutien possible à la livre" if hike else " : pression possible sur la livre") + " si le différentiel avec les taux US évolue dans ce sens ; décision possiblement déjà anticipée.")
                else:
                    add(("USDCHF",), cause + (" : franc potentiellement renforcé, donc baisse possible de USD/CHF" if hike else " : franc potentiellement affaibli, donc hausse possible de USD/CHF") + " à différentiel de taux US inchangé ; décision possiblement déjà anticipée.")
            elif action == "hold":
                add(targets, bank + " maintient son taux : l'effet passe par l'écart au consensus et le message sur les prochaines décisions ; ces éléments manquent pour donner un sens.")
            else:
                add(targets, "communication de la " + bank + " : c'est la trajectoire future des taux par rapport aux anticipations qui affecte le change et le coût du capital ; aucune décision de hausse ou de baisse n'est identifiée.")
        return impacts, [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category

    data_drivers = drivers & {"USD_DATA", "EUR_DATA", "GBP_DATA", "CHF_DATA"}
    if data_drivers and _indicator(headline):
        surprise = _inflation_surprise(headline, description, drivers)
        if surprise == "mixed":
            add(tuple(allowed), "inflation : composantes ou comparaisons au consensus contradictoires ; le taux global et le sous-jacent peuvent entraîner des anticipations de taux opposées, sans flèche unique.")
        elif surprise in ("up", "down"):
            higher = surprise == "up"
            phrase = "inflation au-dessus du consensus" if higher else "inflation sous le consensus"
            if "USD_DATA" in drivers:
                dollar_channel(higher, phrase + ", taux Fed attendus potentiellement " + ("plus élevés" if higher else "moins élevés"))
                add(_INDICES, phrase + (" : taux d'actualisation potentiellement plus élevés, pression possible sur les valorisations." if higher else " : taux d'actualisation potentiellement plus faibles, soutien possible aux valorisations.") + " Cette lecture dépend de la réaction effective des taux.")
            for driver, pair, currency in (("EUR_DATA", "EURUSD", "l'euro"), ("GBP_DATA", "GBPUSD", "la livre"), ("CHF_DATA", "USDCHF", "le franc")):
                if driver in drivers:
                    pair_direction = ("baisse" if higher else "hausse") if driver == "CHF_DATA" else ("hausse" if higher else "baisse")
                    add((pair,), phrase + " : " + pair_direction + " possible si la banque centrale " + ("durcit" if higher else "assouplit") + " sa trajectoire relative à la Fed ; cela passe par " + currency + ".")
                    if driver == "EUR_DATA":
                        add(("GER30",), phrase + (" : financement potentiellement plus coûteux si la BCE durcit sa trajectoire." if higher else " : financement potentiellement moins coûteux si la BCE assouplit sa trajectoire."))
        else:
            add(tuple(allowed), "inflation : le canal est la révision des taux attendus et du coût du capital ; le chiffre précédent ne donne pas l'écart au consensus ; il faut une comparaison de même indicateur, période et unité pour orienter ce canal.")
        return impacts, [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category

    if data_drivers or "CHINA_GROWTH" in drivers:
        if "CHINA_GROWTH" in drivers:
            add(_INDICES, "activité chinoise : les débouchés des exportateurs du DAX et des groupes US dépendent de la demande chinoise ; la surprise au consensus et l'exposition des entreprises déterminent l'effet sur leurs bénéfices.")
        if data_drivers:
            jobs = contains_any(headline, ("payrolls", "nonfarm", "non-farm", "nfp", "jobs", "employment", "unemployment", "jobless claims", "wages"))
            subject = "emploi et salaires" if jobs else "activité et consommation"
            add(_INDICES, subject + " : une amélioration soutient les ventes et bénéfices mais peut relever les taux attendus ; un ralentissement inverse ces deux canaux, donc aucun sens automatique pour l'indice.")
            add(_USD_PAIRS, subject + " : le change dépend de la révision des taux locaux par rapport aux taux de l'autre devise ; le chiffre seul ne tranche pas entre croissance et politique monétaire.")
        return impacts, [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category

    if drivers & {"EARNINGS", "GUIDANCE", "REGULATORY", "LEGAL", "CORPORATE"}:
        clauses = re.split(_CLAUSE_BREAK + r"|,", headline)
        guidance_clauses = [clause for clause in clauses if contains_any(clause, ("guidance", "outlook", "forecast", "forecasts", "profit target"))]
        earnings_clauses = [clause for clause in clauses if clause not in guidance_clauses]
        guidance_text = " ".join(guidance_clauses)
        earnings_text = " ".join(earnings_clauses)
        negative_guidance = _has(guidance_text, r"\b(?:cuts?|cut|lowers?|lowered|slashes?|slashed|reduces?|reduced|withdraws?|withdrawn)\b.{0,35}\b(?:guidance|outlook|forecast|forecasts|profit target)\b")
        positive_guidance = _has(guidance_text, r"\b(?:raises?|raised|lifts?|lifted|boosts?|boosted|increases?|increased)\b.{0,35}\b(?:guidance|outlook|forecast|forecasts|profit target)\b")
        surprise = _combine_surprises(_surprise_one(clause) for clause in earnings_clauses)
        guidance_metric = "de chiffre d'affaires" if contains_any(guidance_text, ("revenue", "sales")) and not contains_any(guidance_text, ("profit", "earnings", "eps")) else "de bénéfices"
        result_metric = "chiffre d'affaires" if contains_any(earnings_text, ("revenue", "sales")) and not contains_any(earnings_text, ("profit", "earnings", "eps")) else "résultats"
        conflicting = (negative_guidance and positive_guidance or surprise == "mixed"
                       or negative_guidance and surprise == "up"
                       or positive_guidance and surprise == "down")
        if drivers & {"REGULATORY", "LEGAL"}:
            fact = "sanction financière confirmée : charge potentielle sur les bénéfices et la trésorerie de la société, selon son traitement comptable et son calendrier de paiement"
        elif conflicting:
            fact = "résultats et perspectives contrastés : les chiffres publiés et la guidance envoient des signaux opposés, sans sens unique pour la contribution de la société"
        elif negative_guidance:
            fact = "perspectives " + guidance_metric + " revues à la baisse : contribution de l'activité de la société potentiellement réduite"
        elif positive_guidance:
            fact = "perspectives " + guidance_metric + " relevées : contribution de l'activité de la société potentiellement accrue"
        elif surprise == "up":
            fact = result_metric + " au-dessus du consensus : meilleure performance publiée, dont la transmission aux bénéfices dépend notamment des coûts"
        elif surprise == "down":
            fact = result_metric + " sous le consensus : performance publiée plus faible, dont la transmission aux bénéfices dépend notamment des coûts"
        elif contains_any(headline, ("fine", "fined", "penalty", "settlement")):
            fact = "sanction financière : charge potentielle sur les bénéfices de la société, distincte de son activité récurrente"
        elif contains_any(headline, ("shares", "stock")) and _direction(headline) in ("up", "down"):
            fact = "mouvement du cours de la société signalé : sa contribution à l'indice varie avec son poids, sans observation de l'indice entier"
        elif "CORPORATE" in drivers or contains_any(headline, ("acquire", "acquires", "acquisition", "merger", "takeover", "buys")):
            fact = "opération d'entreprise : effet sur bénéfices et financement dépendant du prix payé et de l'intégration"
        else:
            fact = "annonce de résultats : la contribution bénéficiaire dépend de l'écart au consensus et des perspectives, absents du titre"
        add(_INDICES, "lecture macro conditionnelle — " + fact + " ; transmission limitée à son poids dans ces indices, sans prédire leur direction globale.")
        return impacts, [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category

    if "OIL" in drivers:
        supply_down = _has(headline, r"\b(?:cuts?|cut|slashes?|slashed|reduces?|reduced|halts?|halted|suspends?|suspended|shuts?|closed|closes?|disrupts?|disrupted|blocks?|blocked)\b.{0,45}\b(?:oil|crude|production|output|supply|exports?|pipeline|hormuz|strait|shipping)\b|\b(?:oil|crude|opec\+?|production|output|supply|exports?|hormuz|strait)\b.{0,45}\b(?:cuts?|cut|halted|disrupted|closed|blocked|blockade|outage|shutdown)\b")
        supply_up = _has(headline, r"\b(?:raises?|raised|boosts?|boosted|increases?|increased|restores?|restored|resumes?|resumed|reopens?|reopened)\b.{0,35}\b(?:oil|crude|production|output|supply|exports?|pipeline|shipping)\b|\b(?:oil|crude|opec\+?|production|output|supply)\b.{0,35}\b(?:increase|increases|increased|boost|boosts|restored|resumed)\b")
        stock_build = _has(headline, r"\b(?:inventories|stocks|stockpiles)\b.{0,30}\b(?:build|builds|rise|rises|rose|increase|increases|surge|grew)\b|\b(?:inventory|stockpile|crude|oil)\b.{0,20}\bbuild\b")
        oil_price = _direction(headline) if contains_any(headline, ("oil prices", "crude prices", "brent", "wti")) else None
        up = supply_down and not supply_up or oil_price == "up"
        down = (supply_up or stock_build) and not supply_down or oil_price == "down"
        if up and not down:
            add(_INDICES, "offre pétrolière réduite ou pétrole en hausse : renchérissement possible de l'énergie et pression sur les marges des consommateurs d'énergie ; les producteurs peuvent en bénéficier.")
            add(("EURUSD", "GBPUSD"), "si le choc rend le pétrole plus cher : facture d'importation énergétique potentiellement accrue en Europe et au Royaume-Uni ; l'effet sur le change dépend aussi des taux et du dollar.")
        elif down and not up:
            add(_INDICES, "offre ou stocks pétroliers en hausse, ou pétrole en baisse : coût énergétique potentiellement réduit pour les entreprises ; une baisse liée à la demande peut aussi signaler des ventes plus faibles.")
            add(("EURUSD", "GBPUSD"), "si cette évolution rend le pétrole moins cher : facture d'importation énergétique potentiellement réduite en Europe et au Royaume-Uni ; le change dépend aussi des taux et du dollar.")
        else:
            add(_INDICES, "annonce pétrolière : l'offre et les stocks modifient le coût de l'énergie et les marges ; le sens du déséquilibre offre-demande manque pour orienter ce canal.")
            add(("EURUSD", "GBPUSD"), "énergie : le montant des importations européennes et britanniques varie avec le prix ; sans variation établie du prix, le canal commercial reste sans sens unique.")

    if "GLOBAL_RISK" in drivers:
        ceasefire_failed = _has(headline, r"\b(?:breaks?|broken|violates?|violated|collapses?|collapsed|ends?|ended|rejects?|rejected)\b.{0,25}\bceasefire\b|\bceasefire\b.{0,25}\b(?:breaks?|broken|collapses?|collapsed|ends?|ended)\b")
        deescalation = contains_any(headline, ("ceasefire", "peace agreement", "peace deal", "ends hostilities", "end hostilities")) and not ceasefire_failed
        funding = contains_any(headline, ("boj", "bank of japan", "carry trade", "carry trades", "yen", "japanese rates"))
        if deescalation:
            add(_INDICES, "cessez-le-feu ou accord de paix : réduction possible de la prime de risque et des perturbations logistiques si l'accord est appliqué ; aucun rebond des indices n'est observé ici.")
            add(("USDCHF",), "désescalade : les flux refuges peuvent se défaire sur le dollar comme sur le franc ; leur différence détermine le sens de USD/CHF.")
        elif funding:
            add(_INDICES, "financement et carry trades : une hausse du coût de financement en yen peut déclencher des ventes de positions financées à crédit ; l'effet dépend de la surprise et de l'ampleur effective des débouclages.")
            add(("USDCHF",), "choc de financement international : dollar et franc peuvent recevoir des flux refuges différents ; aucun sens de USD/CHF ne découle seul de la décision japonaise.")
        else:
            geopolitical = category == "GEO" or contains_any(headline, ("invasion", "war", "missile", "nuclear", "airstrike", "attack", "ceasefire"))
            if geopolitical:
                add(_INDICES, "escalade géopolitique : prime de risque, perturbations logistiques et coûts de financement potentiellement accrus ; leur transmission aux bénéfices ne prouve pas une baisse observée des indices.")
            else:
                add(_INDICES, "stress financier international : retraits de capitaux et financement plus coûteux peuvent peser sur les valorisations ; le sens dépend de la nature du choc et des flux effectifs.")
            add(("USDCHF",), "choc international : dollar et franc sont deux refuges possibles ; le sens de USD/CHF dépend de la force relative de ces flux.")

    if "TRADE" in drivers:
        easing = _has(headline, r"\b(?:lifts?|lifted|removes?|removed|suspends?|suspended|cuts?|cut|reduces?|reduced|scraps?|scrapped|ends?|ended)\b.{0,35}\b(?:tariffs?|duties|sanctions?|embargo|export ban|export controls)\b")
        add(_INDICES, "mesures commerciales : " + ("allègement possible des coûts d'importation et des obstacles aux ventes" if easing else "droits, restrictions ou représailles peuvent modifier les coûts d'importation et les débouchés") + " ; l'effet varie selon les fournisseurs et secteurs de chaque indice.")
        add(("EURUSD", "GBPUSD", "USDCHF"), "commerce extérieur : les flux commerciaux et l'inflation importée peuvent modifier les taux relatifs ; aucune direction de change ne découle du seul tarif.")

    if not impacts and category == "FISCAL":
        add(_INDICES, "mesures budgétaires : impôts et dépenses modifient la demande et les bénéfices, tandis que le financement de la dette peut modifier le coût du capital ; ces canaux peuvent s'opposer.")
        add(_USD_PAIRS, "mesures budgétaires : leur financement et leur effet sur l'inflation déterminent les taux relatifs ; sans ces éléments, pas de sens de change établi.")

    # Aucun rattrapage par une liste d'actifs ou une phrase générique.
    return merge_impacts(impacts), [asset for asset in TRACKED_ASSETS if asset in used_assets], None, category


def priority_label(score):
    if score >= 9:
        return "CRITICAL"
    if score >= 5:
        return "HIGH"
    return "WATCH"
