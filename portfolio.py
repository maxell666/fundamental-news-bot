"""Canaux de transmission vers les sept instruments suivis par l'utilisateur.

Ce filtre de portée complète la sélection fondamentale. Il ne donne ni score
ni direction de cours et n'élargit jamais une société inconnue au S&P 500.
"""

import re
from dataclasses import dataclass

from filter import (
    INDICATORS, SPECULATION, _direct_statement, _event_clause, _monetary_decision,
    _official_monetary_guidance, _supply_effect, contains_any,
    is_noise_story, is_trade_decision, normalize_text,
)


TRACKED_ASSETS = ("EURUSD", "GBPUSD", "GER30", "USDCHF", "SP500", "NAS100", "US30")
USD_PAIRS = ("EURUSD", "GBPUSD", "USDCHF")
US_INDICES = ("SP500", "NAS100", "US30")
ALL_INDICES = ("GER30",) + US_INDICES


@dataclass(frozen=True)
class PortfolioAssessment:
    relevant: bool
    assets: tuple[str, ...] = ()
    drivers: tuple[str, ...] = ()
    reason: str = ""


def _keep(assets, drivers, reason):
    return PortfolioAssessment(
        True, tuple(asset for asset in TRACKED_ASSETS if asset in assets),
        tuple(dict.fromkeys(drivers)), reason,
    )


def _drop(reason):
    return PortfolioAssessment(False, reason=reason)


# Noyau curaté, sans hypothèse sur les poids actuels. Intel n'est plus membre
# du Dow depuis novembre 2024; Oracle et ServiceNow ne sont pas des Nasdaq-100.
# Les petites composantes ne passent que sur un événement matériel explicite.
COMPANY_LINKS = (
    (("apple", "microsoft", "nvidia", "amazon"), ("SP500", "NAS100", "US30"), True),
    (("alphabet", "google", "meta", "tesla", "broadcom", "amd", "intel", "micron", "qualcomm"),
     ("SP500", "NAS100"), True),
    (("oracle", "exxon", "exxonmobil", "berkshire hathaway", "bank of america"), ("SP500",), True),
    (("caterpillar", "jpmorgan", "jp morgan", "goldman sachs", "ibm", "boeing", "chevron",
      "salesforce", "merck", "walmart", "unitedhealth", "visa", "honeywell"), ("SP500", "US30"), True),
    (("fortinet", "doordash"), ("SP500", "NAS100"), False),
    (("servicenow", "service now"), ("SP500",), False),
    (("sap", "siemens", "siemens energy", "allianz", "airbus", "deutsche telekom",
      "munich re", "infineon", "deutsche boerse", "deutsche börse", "dhl"), ("GER30",), True),
    # Liste DAX/Xetra vérifiée le 30 octobre 2026 (Deutsche Börse). Porsche
    # n'y figure plus; ne pas lui attribuer une exposition DAX par héritage.
    (("bmw", "mercedes-benz", "mercedes benz", "volkswagen", "basf", "deutsche bank"), ("GER30",), False),
)

MOVE = r"(?:surges?|surged|plunges?|plunged|plummets?|tumbles?|jumps?|slumps?|rally|rallies|rallied|slides?|drops?|falls?|fell|rises?|rose|gains?|climbs?|sinks?|soars?|rebounds?|hits?)"
DATA = INDICATORS + (
    "ism", "adp", "job openings", "industrial production", "factory activity",
    "services activity", "consumer confidence", "consumer prices", "trade balance",
    "exports", "durable goods", "economic growth", "economy",
)
FINANCIAL = ("earnings", "profit", "profits", "revenue", "sales", "eps", "guidance", "outlook", "forecast")
POLICY = ("rates", "rate", "monetary policy", "quantitative easing", "tightening", "easing",
          "budget", "tax", "taxes", "tariff", "tariffs", "sanctions", "spending", "borrowing", "intervention", "intervenes")
ACTUAL = r"\b(?:reports?|posts?|releases?|unveils?|announces?|cuts?|raises?|hikes?|holds?|held|keeps?|leaves?|grew|grows?|shrinks?|contracts?|expands?|slows?|eases?|accelerates?|rises?|falls?|beats?|tops?|misses?|higher|lower|above|below|unchanged|says?|signals?|declares?|intervenes?|imposes?|lifts?|removes?|approves?|extends?|sanctions|powers?|drives?|supports?|boosts?)\b"
FOREIGN_ROUTINE = ("canada", "canadian", "bank of canada", "boc", "australia", "australian",
                   "rba", "new zealand", "rbnz", "france", "french", "spain", "spanish", "italy", "italian")


def _actual(text):
    return not SPECULATION.search(text) and bool(re.search(ACTUAL, text) or re.search(r"\d[\d.,]*\s*%", text))


def _observed_targets(primary, headline=""):
    if SPECULATION.search(primary) or re.search(r"\b(?:set|poised|due) to\b", primary):
        return ()
    targets = []
    aliases = (
        (("eurusd", "eur/usd"), ("EURUSD",)),
        (("gbpusd", "gbp/usd"), ("GBPUSD",)),
        (("usdchf", "usd/chf"), ("USDCHF",)),
        (("ger30", "ger40", "dax", "dax 40"), ("GER30",)),
        (("sp500", "spx500", "s&p 500", "s&p500"), ("SP500",)),
        (("nasdaq", "nasdaq 100", "nas100"), ("NAS100",)),
        (("dow", "dow jones", "us30"), ("US30",)),
        (("wall street", "us stocks", "u.s. stocks", "us equities"), US_INDICES),
        (("global stocks", "global equities", "world stocks"), ALL_INDICES),
    )
    for terms, assets in aliases:
        names = "|".join(re.escape(term) for term in terms)
        if re.search(rf"\b(?:{names})\b\s+(?:(?:index|futures|is|are|sharply|now)\s+){{0,3}}(?:{MOVE}|(?:ends?|opens?|closes?|trades?|edges?|ticks?|turns?)\s+(?:higher|lower|up|down))\b", primary):
            targets.extend(assets)
    if re.search(rf"^(?:us |u\.s\. )?dollar\s+{MOVE}\b", primary):
        counterpart = re.search(r"\b(?:against|versus|vs\.?)\s+(?:the\s+)?"
                                r"(swiss franc|euro|sterling|pound|yen|yuan|canadian dollar|australian dollar)\b", primary)
        if counterpart:
            target = {"swiss franc": "USDCHF", "euro": "EURUSD", "sterling": "GBPUSD", "pound": "GBPUSD"}.get(counterpart.group(1))
            if target:
                targets.append(target)
        else:
            targets.extend(USD_PAIRS)
    for terms, target in ((("euro",), "EURUSD"), (("sterling", "pound"), "GBPUSD"), (("swiss franc",), "USDCHF")):
        if contains_any(primary, terms) and contains_any(primary, ("dollar", "usd", "greenback")) and re.search(rf"\b{MOVE}\b", primary):
            targets.append(target)
    if (contains_any(primary, ("software stocks", "chip stocks", "semiconductor stocks", "tech stocks"))
            and re.search(rf"\b{MOVE}\b", primary)
            and (contains_any(primary, ("us", "u.s.", "nasdaq"))
                 or any(contains_any(headline or primary, names) and any(asset in US_INDICES for asset in links)
                        for names, links, _ in COMPANY_LINKS))):
        targets.extend(("SP500", "NAS100"))
    return tuple(targets)


def _global_transmission(text):
    return bool(re.search(
        r"\b(?:global|world|wall street|us stocks|us equities|carry trades?)\b.{0,55}"
        r"\b(?:selloff|sell-off|rout|slump|plunge|turmoil|unwind|unwinding|shock|stress|contagion)\b"
        r"|\b(?:unwinds?|unwinding|unwind of)\b.{0,30}\bcarry trades?\b", text,
    ))


def _bond_event(primary, headline):
    us_treasury = contains_any(primary, ("treasury", "treasuries", "us10y", "u.s. 10-year", "us 10-year", "us 10 year"))
    if not us_treasury or SPECULATION.search(primary):
        return None
    movement = re.search(rf"\b(?:yields?|prices?|bonds?|treasuries|us10y)\b.{{0,45}}\b{MOVE}\b", primary)
    auction = contains_any(primary, ("auction",)) and bool(re.search(
        r"\b(?:tails?|tailed|stop(?:s|ped)? through|weak|strong|poor|record|bid.to.cover|awarded|high yield)\b", primary,
    ))
    if movement or auction:
        ten_year = bool(re.search(r"\b(?:10[- ]year|ten[- ]year|us10y)\b", headline))
        return "US10Y" if ten_year else "US_RATES"
    return None


def _oil_shock(primary):
    oil = contains_any(primary, ("oil", "crude", "brent", "wti", "opec", "opec+", "hormuz", "refinery", "refineries", "diesel", "fuel", "gas", "lng"))
    if not oil or SPECULATION.search(primary):
        return False
    if _supply_effect(primary):
        return True
    if is_trade_decision(primary) and contains_any(primary, ("oil", "crude", "diesel", "fuel", "gas", "lng", "refinery", "refineries")):
        return True
    if contains_any(primary, ("oil spill", "oil slick", "pollution", "collision")):
        return False
    if contains_any(primary, ("opec", "opec+")) and contains_any(primary, ("production", "output", "quotas")) and re.search(ACTUAL, primary):
        return True
    if contains_any(primary, ("crude stocks", "oil stocks", "oil inventories", "crude inventories")) and _actual(primary):
        return True
    if re.search(r"\b(?:oil|crude|brent|wti)(?: prices?| futures?)?\s+(?:surges?|plunges?|soars?|tumbles?|plummets?)\b", primary):
        return True
    if re.search(rf"\b(?:oil|crude|brent|wti)(?: prices?| futures?)?\s+{MOVE}\b", primary):
        return any(float(match.replace(",", ".")) >= 3 for match in re.findall(r"([0-9]+(?:[.,][0-9]+)?)\s*%", primary))
    return bool(contains_any(primary, ("hormuz", "oil terminal", "refinery", "refineries"))
                and re.search(r"\b(?:attacks?|attacked|bombed|hit by (?:limpet )?mines|missiles?|airstrikes?)\b", primary))


def _strategic_war_or_ceasefire(primary):
    states = (
        ("us", "u.s.", "united states", "american"), ("iran", "iranian"),
        ("israel", "israeli"), ("russia", "russian"), ("ukraine", "ukrainian"),
        ("china", "chinese"), ("taiwan", "taiwanese"),
        ("uk", "britain", "british"), ("france", "french"), ("germany", "german"),
        ("belarus", "belarusian"), ("north korea",), ("south korea",),
        ("india", "indian"), ("pakistan", "pakistani"), ("saudi arabia",),
    )
    if sum(contains_any(primary, aliases) for aliases in states) < 2:
        return False
    if (SPECULATION.search(primary)
            or re.search(r"\b(?:may|might|could|would|threatens?|threatened|denies?|denied|rejects? reports|no evidence|not|never|fictional|fiction|movie|film|simulation|drill|anniversary)\b", primary)):
        return False
    invasion_or_war = re.search(
        r"\b(?:invades|has invaded|(?:begins?|starts?|launches?)\s+(?:(?:a|the|new|full-scale)\s+){0,3}invasion|"
        r"(?:declares?|enters?|joins?)\s+(?:a\s+)?war|intervenes? militarily|"
        r"(?:deploys?|has deployed)\s+(?:(?:its|new|tactical|strategic)\s+){0,3}nuclear (?:weapons?|warheads?))\b", primary,
    )
    if invasion_or_war:
        return True
    ceasefire = contains_any(primary, ("ceasefire", "peace agreement", "peace deal"))
    local_truce = contains_any(primary, ("local", "humanitarian", "temporary", "train", "railway", "village", "football", "sport", "sports"))
    if local_truce:
        return False
    return ceasefire and bool(re.search(
        r"\b(?:agrees?|agreed|signs?|signed|reaches?|reached|accepts?|accepted|announces?|announced|"
        r"begins?|began|takes? effect|collapses?|collapsed|ends?|ended)\b", primary,
    ))


def assess_portfolio(title, description="", category=None):
    """Sélectionner les instruments liés à un événement fondamental concret."""
    headline = normalize_text(title)
    primary = _event_clause(headline)
    summary = normalize_text(description)
    if not primary or is_noise_story(headline):
        return _drop("Titre vide, récit personnel ou fait divers sans canal vers les instruments suivis")

    # Deux mouvements contemporains explicitement opposés restent deux faits
    # ('DAX rises while Nasdaq falls'), sans lire les rappels historiques.
    observed = tuple(asset for clause in re.split(r"\b(?:while|as)\b|[;,]", headline)
                     for asset in _observed_targets(clause.strip(), headline))
    if observed:
        return _keep(observed, ("OBSERVED_MOVE",), "Mouvement constaté d'un indice ou d'une paire du portefeuille")

    bond = _bond_event(primary, headline)
    if bond:
        assets = USD_PAIRS + ALL_INDICES
        return _keep(assets, (bond,), "Mouvement ou adjudication des Treasuries : coût du financement USD et valorisations")

    company_matches = [(names, assets, major) for names, assets, major in COMPANY_LINKS if contains_any(primary, names)]
    corporate = contains_any(primary, FINANCIAL + ("shares", "stock", "acquire", "buy", "merger", "takeover"))
    observed_company = bool(re.search(rf"\b{MOVE}\b", primary)) and bool(re.search(r"\d[\d.,]*\s*%", primary))
    if company_matches and (category == "EQUITIES" or corporate or observed_company):
        names = tuple(name for names, _, _ in company_matches for name in names)
        company_names = "|".join(re.escape(name) for name in names)
        if re.search(rf"\b(?:{company_names})(?:'s)?\s+(?:customers?|users?|consultants?|suppliers?)\b", primary):
            return _drop("Le sujet est un tiers de la société, sans résultat ni choc indiciel annoncé pour celle-ci")
        announced_guidance = contains_any(primary, FINANCIAL) and _direct_statement(
            primary, names, r"warns?|says?|expects?|forecasts?|raises?|cuts?|lowers?|reduces?|boosts?|withdraws?|reaffirms?|maintains?|sticks to",
        )
        scheduled_report = re.search(r"\b(?:to|due to|set to|scheduled to|will)\s+report\b", primary)
        if scheduled_report and not announced_guidance and not re.search(r"\b(?:reports|reported|posts|posted)\b", primary):
            return _drop("Calendrier de résultats sans nouvelle publication ni guidance annoncée")
        if SPECULATION.search(primary) and not announced_guidance:
            return _drop("Prévision de cours ou hypothèse sur une société, sans fait publié")
        financial_event = contains_any(primary, FINANCIAL) and (_actual(primary) or announced_guidance)
        observed_company = bool(re.search(rf"\b{MOVE}\b", primary))
        stock_subject = contains_any(primary, ("shares", "stock")) or bool(re.match(rf"^(?:{company_names})\s+{MOVE}\b", primary))
        large_move = stock_subject and observed_company and any(float(value.replace(",", ".")) >= 10 for value in re.findall(r"([0-9]+(?:[.,][0-9]+)?)\s*%", primary))
        large_amount = any(float(value.replace(",", ".")) >= 5 for value in re.findall(r"[$€£]\s*(\d[\d.,]*)\s*(?:bn|billion)\b", primary))
        major_deal = bool(re.search(r"\b(?:to buy|to acquire|buys|acquires|merger|takeover)\b", primary)) and large_amount
        legal_event = contains_any(primary, ("fined", "ordered to pay")) and large_amount
        if (financial_event or observed_company or major_deal or legal_event) and (any(major for _, _, major in company_matches) or large_move or major_deal):
            assets = tuple(asset for _, links, _ in company_matches for asset in links)
            driver = ("REGULATORY" if legal_event else "CORPORATE" if major_deal else "GUIDANCE" if announced_guidance or contains_any(primary, ("guidance", "outlook", "forecast", "forecasts")) else "EARNINGS")
            return _keep(assets, (driver,), "Annonce matérielle d'une société du noyau curaté des indices suivis")
        return _drop("Résultat isolé d'une composante secondaire sans choc de cours ni transmission à l'indice")

    if category == "GEO" and _strategic_war_or_ceasefire(primary):
        return _keep(ALL_INDICES + ("USDCHF",), ("GLOBAL_RISK",),
                     "Guerre, déploiement nucléaire ou accord national confirmé entre États stratégiques : prime de risque et flux refuges")

    if _oil_shock(primary):
        return _keep(("EURUSD", "GBPUSD") + ALL_INDICES, ("OIL",),
                     "Choc pétrolier : coûts de l'énergie, inflation et marges des entreprises des indices suivis")

    if contains_any(primary, ("gold", "bullion", "silver")):
        return _drop("Mouvement limité aux métaux précieux, hors instruments suivis")

    if is_trade_decision(primary, summary):
        assets = ()
        if contains_any(primary, ("us", "u.s.", "united states", "white house", "trump", "american")):
            assets += USD_PAIRS + US_INDICES
        if contains_any(primary, ("eu", "european union", "european commission", "germany", "german")):
            assets += ("EURUSD", "GER30")
        if contains_any(primary, ("uk", "britain", "british", "united kingdom")):
            assets += ("GBPUSD",)
        if assets:
            return _keep(assets, ("TRADE",), "Décision commerciale confirmée visant les échanges d'une économie suivie")

    japan = contains_any(primary, ("boj", "bank of japan", "ueda", "japan", "japanese"))
    if japan:
        surprise = contains_any(headline, ("surprise", "unexpected", "unexpectedly", "emergency", "shock"))
        linked_summary = any(
            _global_transmission(sentence)
            and contains_any(sentence, ("boj", "japan", "japanese", "yen", "carry trade", "carry trades"))
            and re.search(r"\b(?:triggers?|drives?|sparks?|causes?|unwinds?|unwinding|spillover|spills?)\b", sentence)
            for sentence in re.split(r"[.!?]", summary)
        )
        global_effect = _global_transmission(headline) or linked_summary
        if global_effect or (surprise and contains_any(primary, ("rate", "rates", "monetary", "intervention")) and _actual(primary)):
            return _keep(ALL_INDICES + ("USDCHF",), ("GLOBAL_RISK",),
                         "Surprise japonaise ou transmission mondiale explicite via financement, carry trades et risque")
        return _drop("Annonce japonaise courante sans surprise ni transmission mondiale explicite")

    if contains_any(primary, ("china", "chinese")) and contains_any(primary, ("gdp", "pmi", "industrial production", "factory activity", "exports", "property crisis", "banking crisis")) and _actual(primary):
        assets = ("GER30",)
        if _global_transmission(headline) or contains_any(primary, ("us companies", "us earnings", "wall street", "nasdaq")):
            assets += US_INDICES
        return _keep(assets, ("CHINA_GROWTH",), "Activité ou stress chinois : débouchés industriels et exportateurs allemands")

    political_economy = contains_any(primary, DATA + POLICY)
    scopes = (
        (("fed", "fomc", "federal reserve", "powell", "warsh", "us", "u.s.", "united states", "american", "white house", "trump", "congress", "us treasury"), USD_PAIRS + US_INDICES, "USD"),
        (("ecb", "european central bank", "lagarde", "eurozone", "euro zone", "euro area", "germany", "german"), ("EURUSD", "GER30"), "EUR"),
        (("boe", "bank of england", "bailey", "uk", "united kingdom", "britain", "british", "chancellor"), ("GBPUSD",), "GBP"),
        (("snb", "swiss national bank", "switzerland", "swiss", "schlegel"), ("USDCHF",), "CHF"),
    )
    # Le pays explicitement nommé dans l'annonce prime sur tout rappel du Fed
    # dans le résumé d'un chiffre canadien ou australien.
    monetary_guidance = _official_monetary_guidance(primary, primary + " " + summary)
    foreign_names = "|".join(re.escape(name) for name in FOREIGN_ROUTINE)
    foreign_subject = bool(re.match(rf"^(?:the\s+)?(?:{foreign_names})\b", primary))
    if foreign_subject and _global_transmission(headline):
        return _keep(ALL_INDICES + ("USDCHF",), ("GLOBAL_RISK",), "Transmission explicite d'un événement étranger aux marchés mondiaux suivis")
    monetary_decision = _monetary_decision(primary, primary + " " + summary)
    scope_text = primary
    if monetary_decision and not foreign_subject:
        bank_scopes = (
            (("fed", "fomc", "federal reserve"), "fed"),
            (("ecb", "european central bank"), "ecb"),
            (("boe", "bank of england"), "boe"),
            (("snb", "swiss national bank"), "snb"),
        )
        if not any(contains_any(primary, aliases) for aliases, _ in bank_scopes):
            lead = re.split(r"[.!?]", summary, maxsplit=1)[0]
            banks = [bank for aliases, bank in bank_scopes if contains_any(lead, aliases)]
            if len(banks) == 1:
                scope_text += " " + banks[0]
    if not foreign_subject and political_economy and (_actual(primary) or monetary_guidance or monetary_decision):
        for aliases, assets, currency in scopes:
            if contains_any(scope_text, aliases):
                policy = (category in ("FISCAL", "TRADE") or monetary_guidance
                          or monetary_decision
                          or (contains_any(primary, POLICY) and not contains_any(primary, DATA)))
                drivers = (currency + ("_POLICY" if policy else "_DATA"),)
                if category == "TRADE":
                    drivers += ("TRADE",)
                if currency == "USD" and (monetary_decision or _global_transmission(headline)
                                          or contains_any(primary, ("eu", "european union", "germany", "global tariffs"))):
                    assets += ("GER30",)
                return _keep(assets, drivers, "Annonce économique ou monétaire directement liée à " + currency)
        if contains_any(primary, ("pce", "nonfarm payrolls", "non-farm payrolls", "nfp", "jobless claims")):
            return _keep(USD_PAIRS + US_INDICES, ("USD_DATA",), "Indicateur américain identifié dans le titre")

    if category in ("TRADE", "GEO") and _global_transmission(headline):
        return _keep(ALL_INDICES + ("USDCHF",), ("GLOBAL_RISK",), "Transmission mondiale explicite aux actions et au risque financier")
    if category == "EQUITIES":
        return _drop("Société sans lien vérifié avec le noyau des indices suivis")
    return _drop("Aucun canal direct identifié vers EURUSD, GBPUSD, GER30, USDCHF ou les trois indices US")
