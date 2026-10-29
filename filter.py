"""Sélection prudente d'événements macro, énergie et géopolitiques.

Un sujet sensible ne suffit pas : il faut une annonce ou un mouvement concret.
Le titre reste déterminant ; le résumé ne peut pas sauver un témoignage ou
un avertissement général. Règles destinées aux sources anglophones du bot.
"""

import html
import re
from dataclasses import dataclass
from functools import lru_cache


FILTER_VERSION = "pertinence-v3.0"


def normalize_text(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return " ".join(text.lower().replace("’", "'").replace("–", "-").split())


@lru_cache(maxsize=512)
def _term_pattern(term):
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)")


def contains_any(text, terms):
    """Mots entiers : 'war' ne correspond pas à 'award', ni 'gas' à 'Gaza'."""
    text = normalize_text(text)
    return any(_term_pattern(term).search(text) for term in terms)


@dataclass(frozen=True)
class Assessment:
    score: int
    reason: str
    category: str = "FONDAMENTAL"

    @property
    def relevant(self):
        return self.score > 0


# Ces formats sont rejetés même si le résumé rappelle une guerre ou un choc
# pétrolier. On préfère manquer une reformulation à envoyer ces récits locaux.
PERSONAL_STORIES = (
    "my wife", "my husband", "my family", "my friend", "i survived",
    "survivor", "survivors", "tells her story", "tells his story",
    "scared to", "afraid to", "fear for", "childminder", "shark",
    "crocodile", "footballer", "celebrity", "singer", "chess",
    "heating bills", "heating oil customers", "home heating oil",
)
PERSONAL_PATTERN = re.compile(
    r"\b(?:woman|man|family|families|household|households|pensioner|pensioners|"
    r"resident|residents|mother|father|tourist|tourists|sailors)\b.{0,100}"
    r"\b(?:heating|bills?|afford|scared|afraid|fear|struggl\w*|surviv\w*|"
    r"stressed|exhausted|trapped|killed)\b"
)
GENERAL_WARNINGS = re.compile(
    r"\b(?:must|should|needs? to|urged to)\b.{0,60}"
    r"\b(?:prepare|be ready|be prepared|brace|stockpile)\b"
    r"|\b(?:prepare|preparing|preparedness|readiness)\b.{0,60}"
    r"\b(?:emergencies|emergency|hostile acts|war|conflict)\b"
    r"|\b(?:sabre-rattling|saber-rattling)\b"
)
EDITORIAL = re.compile(
    r"(?:^|:\s*)(?:why|how|what|could|will|should|can|would|is|are)\b"
    r"|^(?:watch|listen|analysis|opinion):"
    r"|\b(?:explained|explainer|opinion|what we know|what to expect|"
    r"could|might|may (?:cut|hold|raise|close|attack|impose|reopen|resume|halt|increase|reduce|begin|start|launch|invade)|"
    r"expected to|hold expected|likely to|threatens? to|considers?|"
    r"considering|weighs?|discusses?|discussing|debates?|plans? to|"
    r"talks|negotiations|offers?|wants?|urges?|warns? .{0,30}(?:will|if)|"
    r"if|footage|anniversary|years? (?:on|ago))\b"
)

CENTRAL_BANKS = (
    "fed", "fomc", "federal reserve", "ecb", "european central bank",
    "boe", "bank of england", "bank of japan", "boj", "central bank",
    "powell", "lagarde", "bank of canada", "boc", "reserve bank of australia",
    "rba", "reserve bank of new zealand", "rbnz", "swiss national bank", "snb",
    "reserve bank of india", "rbi",
)
INDICATORS = (
    "cpi", "pce", "ppi", "inflation", "nonfarm payrolls", "non-farm payrolls",
    "nfp", "jobs report", "payrolls", "unemployment", "gdp", "pmi",
    "retail sales", "jobless claims",
)
MACRO_ECONOMIES = (
    "us", "u.s.", "united states", "american", "uk", "united kingdom",
    "britain", "british", "england", "eurozone", "euro area", "european union",
    "germany", "german", "france", "french", "italy", "spain", "china",
    "chinese", "japan", "japanese", "canada", "canadian", "australia",
    "australian", "new zealand", "switzerland", "swiss", "india", "indian",
)
LOCAL_MACRO = (
    "island", "isle of man", "jersey", "guernsey", "channel islands",
    "local inflation", "regional inflation", "county", "counties", "council",
)
US_INDICATORS = ("pce", "nonfarm payrolls", "non-farm payrolls", "nfp", "jobless claims")
STRATEGIC = (
    "strait of hormuz", "hormuz", "red sea", "suez", "oil tanker",
    "oil tankers", "tanker", "tankers", "shipping", "trade route",
    "trade routes", "oil terminal", "pipeline", "refinery", "oilfield",
    "nuclear facility", "nuclear facilities", "nuclear site", "nuclear sites",
    "nuclear plant", "military base", "military bases",
)
COUNTRIES = (
    "iran", "iranian", "israel", "israeli", "russia", "russian",
    "ukraine", "ukrainian", "china", "chinese", "taiwan", "taiwanese",
    "us", "u.s.", "united states", "uk", "britain", "british",
    "european union", "eu", "nato", "houthi", "houthis", "saudi arabia",
    "north korea", "south korea", "india", "pakistan",
)
COUNTRY_GROUPS = (
    ("iran", "iranian"), ("israel", "israeli"), ("russia", "russian"),
    ("ukraine", "ukrainian"), ("china", "chinese"), ("taiwan", "taiwanese"),
    ("us", "u.s.", "united states"), ("uk", "britain", "british"),
    ("nato",), ("houthi", "houthis"), ("saudi arabia",),
    ("north korea",), ("south korea",), ("india",), ("pakistan",),
)

TRADE_ACTORS = COUNTRIES + MACRO_ECONOMIES + (
    "white house", "trump", "european commission", "downing street",
    "beijing", "kremlin", "ottawa", "washington", "mexico", "mexican",
    "chancellor", "treasury", "finance minister",
)
US_MEGACAPS = ("apple", "microsoft", "nvidia", "alphabet", "google", "amazon", "meta", "tesla")
US_INDEX_COMPANIES = US_MEGACAPS + (
    "broadcom", "amd", "advanced micro devices", "micron", "intel", "qualcomm",
    "oracle", "salesforce", "cisco", "adobe", "netflix", "jpmorgan", "jp morgan",
    "goldman sachs", "bank of america", "wells fargo", "citigroup", "morgan stanley",
    "berkshire hathaway", "walmart", "exxon", "exxonmobil", "chevron", "eli lilly",
    "unitedhealth", "visa", "mastercard", "doordash", "instacart", "boeing",
    "caterpillar", "servicenow", "service now", "fortinet", "palantir", "ibm",
    "honeywell", "johnson & johnson", "procter & gamble", "costco", "home depot",
    "mcdonald's", "coca-cola", "pepsico", "abbvie", "merck", "applied materials",
    "lam research", "intuitive surgical",
)
RATE_TOPICS = (
    "rate", "rates", "borrowing costs", "inflation", "monetary policy",
    "easing", "tightening", "recession", "employment", "unemployment",
)
FISCAL_MEASURES = (
    "tax", "taxes", "bank tax", "bank levy", "tax thresholds", "fuel duty",
    "spending", "public borrowing", "borrowing", "deficit", "debt ceiling",
    "income tax", "capital gains", "corporation tax", "national insurance",
    "fiscal stimulus", "stimulus package", "shutdown", "spending cuts",
)
EDITORIAL_FORMAT = re.compile(
    r"(?:^|:\s*)(?:why|how|what|could|will|should|can|would|is|are)\b"
    r"|^(?:watch|listen|analysis|opinion):|\b(?:explainer|explained|anniversary)\b"
)
SPECULATION = re.compile(
    r"\b(?:could|might|would|expected to|likely to|forecast to|considering|considers?|"
    r"weighs?|mulls?|rumou?rs?|preliminary|in talks|talks to|plans? to|"
    r"may (?:be|buy|acquire|cut|hold|raise|close|attack|impose|reopen|resume|halt|"
    r"increase|reduce|begin|start|launch|invade)|if|"
    r"(?:analysts?|economists?|traders?|investors?|markets?)\b.{0,45}\b"
    r"(?:expect|forecast|bet|hope|predict))\b"
)


def _event_clause(title):
    """Évaluer l'annonce avant son contexte causal, sans supprimer un 'if'."""
    if re.match(r"^(?:after|as|amid|despite|following|while|although|since|during)\b", title) and "," in title:
        title = title.split(",", 1)[1].strip()
    return re.split(
        r"\b(?:after|as|amid|while|despite|but|although|following|because|since|during|"
        r"on (?:hopes|expectations|fears|reports))\b", title, maxsplit=1
    )[0].strip(" ,;:-")


def is_trade_decision(title, description=""):
    context = normalize_text(f"{title} {description}")
    title = _event_clause(normalize_text(title))
    if (EDITORIAL.search(title) or SPECULATION.search(title)
            or _matches(title, r"\b(?:discussions?|talks?|negotiations?)\b.{0,60}\b(?:to|about|over)\b")):
        return False
    if (contains_any(title, ("sanction", "sanctions"))
            and not contains_any(title, ("tariff", "tariffs", "embargo", "import duties", "export ban", "export controls"))):
        target = re.split(r"\bsanctions?\b", title, maxsplit=1)[-1]
        strategic_target = contains_any(target, (
            "iran", "iranian", "russia", "russian", "china", "chinese", "taiwan", "taiwanese",
            "north korea", "saudi arabia", "venezuela",
        ))
        financial_channel = contains_any(title, (
            "oil", "gas", "crude", "lng", "bank", "banks", "banking", "financial",
            "finance", "investment", "exports", "imports", "semiconductors", "chips",
            "energy", "shipping", "payments", "assets", "debt",
        ))
        if not (strategic_target or financial_channel):
            return False
    # 'Raises concerns over tariffs' ne signifie pas 'raises tariffs'.
    action_text = re.sub(
        r"\b(?:raises?|raised|increases?|increased)\s+(?:concerns?|fears?|questions?|doubts?)\b",
        "", title,
    )
    return (
        contains_any(title, ("tariff", "tariffs", "sanction", "sanctions", "embargo",
                             "import duties", "export ban", "export bans", "export controls"))
        and contains_any(context, TRADE_ACTORS)
        and (_matches(action_text, r"\b(?:imposes?|imposed|announces?|announced|approves?|"
                     r"approved|enacts?|enacted|lifts?|lifted|removes?|removed|"
                     r"suspends?|suspended|raises?|raised|increases?|increased|"
                     r"cuts?|extends?|extended|ends?|ended|scraps?|scrapped|"
                     r"slashes?|slashed|reduces?|reduced|eases?|eased|tightens?|tightened|"
                     r"doubles?|doubled|introduces?|introduced|takes? effect|comes? into force)\b")
             or _matches(action_text, r"^(?:us|u\.s\.|eu|uk|britain|united states|us treasury)\s+"
                                      r"sanctions\s+(?!on\b|against\b)\w"))
    )


def is_major_company_penalty(title):
    """Amende confirmée d'au moins 5 milliards sur une mégacapitalisation US."""
    original_title = normalize_text(title)
    title = _event_clause(original_title)
    if (EDITORIAL.search(title) or _matches(title, r"\bmay\s+(?:be\s+)?fined\b")
            or not contains_any(title, US_MEGACAPS)):
        return False
    penalty = _matches(title, r"\b(?:fined|ordered to pay|(?:hit with|handed|receives?|received)\b.{0,30}\bfine|"
                             r"fine\b.{0,30}\b(?:overturned|cancelled|scrapped))\b")
    appeal = _matches(title, r"\bwins? (?:court )?appeal\b") and contains_any(original_title, ("fine", "penalty"))
    if not (penalty or appeal):
        return False
    magnitude_text = original_title if appeal else title
    money = (r"[$€£]\s*(\d+(?:[.,]\d+)?)\s*(?:bn|billion)\b|"
             r"(\d+(?:[.,]\d+)?)\s*billion\s+(?:dollars?|euros?|pounds?)\b")
    for match in re.finditer(money, magnitude_text):
        amount = next(group for group in match.groups() if group is not None)
        if float(amount.replace(",", ".")) < 5:
            continue
        before = magnitude_text[max(0, match.start() - 50):match.start()]
        after = magnitude_text[match.end():]
        # Le montant doit concerner la sanction, pas un investissement cité à côté.
        if (re.search(r"\b(?:fined|ordered to pay|hit with|handed|fine of|penalty of)\s+"
                      r"(?:(?:an?|record|antitrust|privacy)\s+){0,3}$", before)
                or re.match(r"\s+(?:(?:antitrust|privacy|data-protection|record)\s+){0,3}"
                            r"(?:fine|penalty)\b", after)):
            return True
    return False


def _matches(text, pattern):
    return bool(re.search(pattern, text))


def is_noise_story(text):
    text = normalize_text(text)
    # Un mot comme 'families' dans une décision fiscale nationale ne transforme
    # pas cette décision en témoignage. Le récit personnel doit être le sujet.
    personal_lead = _matches(
        text, r"^[\"']?(?:i\b|my\b|we\b|woman\b|man\b|famil(?:y|ies)\b|"
              r"households?\b|pensioners?\b|residents?\b|mother\b|father\b|"
              r"tourists?\b|sailors\b|survivors?\b|childminder\b|"
              r"home heating oil\b|heating oil customers\b)"
    )
    unmistakable_story = contains_any(text, (
        "i survived", "my wife", "my husband", "my family", "tells her story",
        "tells his story", "chess", "footballer", "celebrity", "shark", "crocodile",
    ))
    return unmistakable_story or (personal_lead and (
        bool(PERSONAL_PATTERN.search(text))
        or contains_any(text, PERSONAL_STORIES)
        or contains_any(text, ("heating", "bills", "afford", "killed", "survived"))
    ))


def _supply_effect(title):
    # Relier la fermeture/interruption à l'infrastructure ou aux flux eux-mêmes.
    # "Beaches closed near an oil terminal" n'est pas une fermeture du terminal.
    target = (
        r"(?:strait of hormuz|hormuz|suez(?: canal)?|red sea shipping|"
        r"shipping(?: lanes| routes)?|trade routes?|pipelines?|refiner(?:y|ies)|"
        r"oil terminals?|oilfields?|(?:oil|crude(?: oil)?|gas|lng|energy) "
        r"(?:exports?|production|supply|output|flows?))"
    )
    action = (
        r"(?:halts?|halted|stops?|stopped|suspends?|suspended|shuts?|"
        r"closed|closes?|blockaded|blocked|blocks?|disrupted|disrupts?|"
        r"shutdown|outages?|resumes?|resumed|reopens?|reopened|"
        r"cuts? off|cut off|closure of)"
    )
    modifiers = r"(?:(?:the|a|an|all|key|major|main|critical|oil|gas|uae|iranian|russian)\s+){0,5}"
    auxiliary = r"(?:\s+(?:is|are|was|were|has|have|been|being|now|still|partly|partially|fully|temporarily|indefinitely|reportedly|remains?|to|be|will)){0,6}"
    return (_matches(title, rf"\b{action}\b\s+{modifiers}{target}\b")
            or _matches(title, rf"\b{target}\b{auxiliary}\s+{action}\b"))


def _market_move(title):
    benchmarks = (
        "oil prices", "crude prices", "brent", "wti", "oil", "gold", "dollar",
        "treasury yields", "us treasury yields", "bond yields", "gilt yields", "uk gilt yields",
        "bund yields", "wall street", "nasdaq", "s&p 500", "s&p500", "dow jones", "dow",
        "natural gas prices", "stock markets", "global stocks", "us stocks", "u.s. stocks",
        "european stocks", "asian stocks", "software stocks", "tech stocks", "bank stocks",
        "semiconductor stocks", "chip stocks", "stocks", "equities", "stock futures",
        "us stock futures", "sterling", "pound", "euro", "yen",
    )
    subject = "|".join(re.escape(term) for term in sorted(benchmarks, key=len, reverse=True))
    # Lier le mouvement à l'actif: 'oil spill hits beaches' et 'gold mining
    # company shares jump' ne décrivent pas le cours du pétrole ou de l'or.
    bridge = (r"(?:(?:prices?|crude|oil|futures?|index|indices|yields?|are|is|has|have|"
              r"now|sharply|slightly|strongly|again|further)\s+){0,5}")
    movement = (r"(?:surges?|surged|plunges?|plunged|soars?|soared|tumbles?|tumbled|"
                r"jumps?|jumped|slumps?|slumped|rallies|rallied|slides?|slid|rises?|rose|"
                r"falls?|fell|hits?|hit|drops?|dropped|sinks?|sank|rebounds?|rebounded|"
                r"gains?|gained|weakens?|weakened|strengthens?|strengthened|"
                r"(?:edges?|ticks?|opens?|closes?|ends?|turns?)\s+(?:up|down|higher|lower))")
    return _matches(
        title, rf"^(?:(?:global markets|markets|market update|live updates):\s*)?"
               rf"(?:{subject})\b\s+{bridge}{movement}\b"
    )


def _direct_statement(title, actors, verbs):
    """Une déclaration de l'acteur, distincte d'une anticipation d'analyste."""
    for actor in actors:
        match = _term_pattern(actor).search(title)
        if not match or match.start() > 30:
            continue
        if contains_any(title[:match.start()], ("analyst", "analysts", "economist", "economists", "traders")):
            continue
        tail = title[match.end():]
        statement = re.match(rf"(?:'s)?\s+(.*?)\b(?:{verbs})\b", tail)
        if not statement:
            continue
        between = statement.group(1).strip()
        if len(between.split()) <= 4 and not contains_any(between, (
            "analysts", "profits", "earnings", "revenue", "sales", "shares",
            "could", "might", "may", "expected", "to",
        )):
            return True
    return False


def _official_monetary_guidance(title, context):
    if not (_reference_bank_in_scope(title, context) and contains_any(title, RATE_TOPICS)):
        return False
    return _direct_statement(
        title, CENTRAL_BANKS,
        r"says?|said|signals?|warns?|rules? out|opens? (?:the )?door|pledges?|"
        r"sees?|expects?|indicates?|hints?|cautions?",
    )


def _reference_bank_in_scope(title, context):
    named = tuple(bank for bank in CENTRAL_BANKS if bank != "central bank")
    if contains_any(title, named):
        return True
    if contains_any(title, ("central bank",)):
        return contains_any(title, MACRO_ECONOMIES)
    if _matches(title, r"\bbank of\b|\bbanks?\b"):
        return False
    # Un titre elliptique ('Interest rates held') peut être précisé par le
    # résumé. Le résumé ne remplace pas un pays explicitement hors périmètre.
    return contains_any(context, named)


def _monetary_decision(title, context):
    if not _reference_bank_in_scope(title, context):
        return False
    instrument = (r"(?:(?:interest|key|policy|cash|deposit|funds|overnight|lending|"
                  r"benchmark|main|bank)\s+){0,3}rates?|borrowing costs")
    modifiers = r"(?:(?:the|a|its|their|all|benchmark|main|key|policy)\s+){0,4}"
    verb = (r"(?:cuts?|raised?|raises|hikes?|hiked|slashes?|slashed|lowers?|lowered|"
            r"holds?|held|keeps?|kept|maintains?|maintained|leaves?|left|increases?|"
            r"increased|reduces?|reduced)")
    direct = _matches(title, rf"\b{verb}\s+{modifiers}(?:{instrument})\b")
    passive = _matches(
        title, rf"\b(?:{instrument})\b\s+"
               r"(?:(?:is|are|was|were|has|have|been|left|kept|remain|remains)\s+){0,4}"
               r"(?:cut|raised|hiked|lowered|held|maintained|unchanged|on hold)\b"
    )
    announced = _matches(
        title, r"\b(?:announces?|announced|approves?|approved|delivers?|delivered)\b"
               r".{0,35}\brate (?:cuts?|hikes?|increase|reduction)\b"
    )
    labelled = (contains_any(title, ("rate decision", "decision"))
                and _matches(title, r"\b(?:hikes?|cuts?|increase|reduction)\s+(?:to|by)\s+\d"))
    return direct or passive or announced or labelled


def _billion_amounts(text):
    pattern = (r"[$€£]\s*(\d+(?:[.,]\d+)?)\s*(?:bn|billion)\b|"
               r"(\d+(?:[.,]\d+)?)\s*billion\s+(?:dollars?|euros?|pounds?)\b")
    return [float(next(value for value in match.groups() if value is not None).replace(",", "."))
            for match in re.finditer(pattern, text)]


def _corporate_event(title, context):
    known_company = contains_any(title, US_INDEX_COMPANIES)
    financial_topic = contains_any(title, (
        "earnings", "profit", "profits", "revenue", "revenues", "sales", "eps",
        "guidance", "outlook", "forecast", "forecasts", "margin", "margins", "results",
    ))
    direct_guidance = known_company and financial_topic and _direct_statement(
        title, US_INDEX_COMPANIES,
        r"warns?|says?|said|sees?|expects?|forecasts?|raises?|cuts?|lowers?|"
        r"reduces?|boosts?|withdraws?|reaffirms?|maintains?",
    )
    scheduled_report = _matches(
        title, r"\b(?:to|due to|set to|scheduled to|will)\s+report\b"
    )
    already_published = _matches(title, r"\b(?:reports|reported|posts|posted|releases|released)\b")
    guidance_detail = _matches(
        title, r"[$€£]\s*\d|\d[\d.,]*\s*(?:%|(?:billion|bn)\b)|"
               r"\b(?:higher|lower|stronger|weaker)\s+(?:revenue|sales|earnings|profits|eps)\b|"
               r"\b(?:revenue|sales|earnings|profits|eps)\b.{0,15}\b(?:higher|lower|grow|fall|rise|decline)\b"
    )
    if known_company and financial_topic and scheduled_report and not (
            already_published or (direct_guidance and guidance_detail)):
        return Assessment(0, "Calendrier de résultats sans nouveau chiffre ni guidance annoncée")
    if direct_guidance:
        return Assessment(7, "Résultats attendus ou guidance annoncés par une grande valeur US", "EQUITIES")

    if SPECULATION.search(title):
        return None
    price_action = r"(?:surges?|plunges?|soars?|tumbles?|jumps?|slumps?|rallies|slides?|drops?|sinks?|rebounds?|falls?|rises?)"
    company_names = "|".join(re.escape(company) for company in sorted(US_INDEX_COMPANIES, key=len, reverse=True))
    direct_price = (_matches(title, rf"^(?:{company_names})\b\s+{price_action}\b")
                    and _matches(title, r"\d[\d.,]*\s*%"))
    if (known_company and (contains_any(title, ("shares", "stock")) or direct_price)
            and _matches(title, rf"\b{price_action}\b")):
        return Assessment(7, "Mouvement explicite du cours d'une grande valeur US", "EQUITIES")
    earnings_preview = _matches(title, r"\b(?:earnings preview|ahead of (?:its )?(?:q[1-4] )?earnings)\b")
    if (known_company and financial_topic and (not earnings_preview or already_published) and _matches(
            title, r"\b(?:reports|reported|posts|posted|beats?|beat|misses?|missed|tops?|topped|"
                   r"surges?|surged|soars?|soared|rises?|rose|falls?|fell|doubles?|doubled|"
                   r"triples?|tripled|jumps?|jumped|drops?|dropped|declines?|declined|"
                   r"climbs?|climbed|above|below|record|higher|lower)\b")):
        return Assessment(8, "Publication de résultats d'une grande valeur US", "EQUITIES")

    corporate_context = known_company or contains_any(context, (
        "company", "companies", "firm", "merger", "takeover", "acquisition", "shareholders",
    ))
    acquisition = _matches(
        title, r"\b(?:to buy|buys?|bought|to acquire|acquires?|acquired|"
               r"merges? with|merger|takeover|buyout|acquisition)\b"
    )
    confirmed_deal = _matches(
        title, r"\b(?:to buy|to acquire|buys?|bought|acquires?|acquired|agrees?|agreed|"
               r"announces?|announced|signs?|signed|deal|merges?|approved)\b"
    )
    major_amount = any(amount >= 5 for amount in _billion_amounts(context))
    large_parties = sum(contains_any(title, (company,)) for company in US_INDEX_COMPANIES) >= 2
    if corporate_context and acquisition and confirmed_deal and (major_amount or large_parties):
        return Assessment(7, "Acquisition ou fusion majeure annoncée", "EQUITIES")
    return None


def _fiscal_decision(title, context):
    if contains_any(title, LOCAL_MACRO + ("mayor", "borough", "municipal", "parish", "local authority")):
        return None
    national_scope = contains_any(context, MACRO_ECONOMIES + (
        "chancellor", "treasury", "white house", "congress", "downing street", "finance minister",
    ))
    if not national_scope or SPECULATION.search(title):
        return None
    substantive = contains_any(title, FISCAL_MEASURES)
    action = _matches(
        title, r"\b(?:unveils?|unveiled|announces?|announced|presents?|presented|"
               r"introduces?|introduced|raises?|raised|hikes?|hiked|cuts?|cut|"
               r"reduces?|reduced|increases?|increased|freezes?|frozen|scraps?|scrapped|"
               r"extends?|extended|approves?|approved|passes?|passed|signs?|signed|"
               r"keeps?|kept|remain(?:s)? unchanged|sets? out)\b"
    )
    if substantive and action:
        return Assessment(7, "Décision fiscale ou budgétaire nationale", "FISCAL")
    budget_release = contains_any(title, ("budget", "fiscal statement", "spending review")) and _matches(
        title, r"\b(?:unveils?|unveiled|announces?|announced|presents?|presented|"
               r"sets? out|publishes?|published|key points|at a glance)\b"
    )
    if (budget_release and contains_any(context, FISCAL_MEASURES)
            and _matches(context, r"\b(?:announced|unveiled|introduced|raised|cut|"
                         r"frozen|new|kept|spending|tax)\b")):
        return Assessment(7, "Publication de mesures budgétaires nationales", "FISCAL")
    if (contains_any(title, ("departments", "ministries"))
            and _matches(title, r"\b(?:tells?|orders?|instructs?|requires?)\b")
            and _matches(title, r"\d[\d.,]*\s*%\s*cuts?\b")
            and contains_any(context, ("public spending", "government spending", "budget", "chancellor"))):
        return Assessment(7, "Réallocation annoncée des dépenses publiques", "FISCAL")
    return None


def assess_news(title, description=""):
    """Source commune du filtre et du score ; 0 signifie rejet.

    L'événement doit apparaître dans le titre. Le résumé peut préciser le sujet
    (ex. le nom de la banque), mais pas créer un événement absent du titre.
    Les scores sont des priorités de règles, pas des probabilités d'impact.
    """
    title = normalize_text(title)
    context = normalize_text(f"{title} {description}")
    if not title:
        return Assessment(0, "Titre vide")
    if is_noise_story(title):
        return Assessment(0, "Témoignage, fait divers ou sujet de consommation locale")
    if GENERAL_WARNINGS.search(title):
        return Assessment(0, "Avertissement général ou préparation hypothétique")
    original_title = title
    title = _event_clause(title)
    if EDITORIAL_FORMAT.search(title) or title.endswith("?"):
        return Assessment(0, "Analyse, question ou scénario hypothétique")

    # Une déclaration de Powell ou un avertissement de résultats est en soi
    # une information publiée. 'Could/may' dans cette déclaration ne justifie
    # pas le même rejet qu'une anticipation d'analyste non attribuée.
    if _official_monetary_guidance(title, context):
        return Assessment(7, "Orientation monétaire déclarée par une banque centrale", "MACRO")
    corporate = _corporate_event(title, context)
    if corporate is not None:
        return corporate
    if _matches(title, r"\b(?:data spotlight|news wrap|preview|pricing in|odds of|chance of|rate hike bets)\b"):
        return Assessment(0, "Prévision de marché ou synthèse, sans nouvelle décision annoncée")
    if is_trade_decision(title, context):
        return Assessment(8, "Décision de sanctions ou de politique commerciale", "TRADE")
    fiscal = _fiscal_decision(title, context)
    if fiscal is not None:
        return fiscal
    if EDITORIAL.search(title) or SPECULATION.search(title):
        return Assessment(0, "Projection ou discussion sans annonce de marché confirmée")

    supply_effect = _supply_effect(title)
    market_move = _market_move(title)
    local_incident = contains_any(title, (
        "oil spill", "oil spills", "oil slick", "oil slicks", "collision",
        "tanker accident", "pollution",
    ))
    if local_incident and not (supply_effect or market_move):
        return Assessment(0, "Pollution ou accident local sans effet explicite sur les flux ou les marchés")

    # Un 'rate hike' nominal dans un pari n'est pas une décision. La relation
    # verbe/instrument ou un libellé de décision explicite doit être présent.
    if _monetary_decision(title, context):
        return Assessment(9, "Décision de politique monétaire", "MACRO")

    if (contains_any(title, INDICATORS)
            and _matches(title, r"\d[\d.,]*\s*(?:%|percent|per cent)|"
                         r"\b(?:rises?|rose|falls?|fell|slows?|slowed|cools?|cooled|eases?|eased|"
                         r"accelerates?|accelerated|jumps?|jumped|drops?|dropped|contracts?|"
                         r"expands?|beats?|misses?|higher|lower|highest|lowest|unchanged|released)\b")):
        if contains_any(title, LOCAL_MACRO):
            return Assessment(0, "Statistique économique locale hors périmètre macro")
        if not (contains_any(context, MACRO_ECONOMIES) or contains_any(title, US_INDICATORS)):
            return Assessment(0, "Portée nationale ou économie de référence non identifiée")
        return Assessment(8, "Publication ou variation d'un indicateur macroéconomique", "MACRO")

    if (contains_any(title, ("economy", "economic growth", "consumer prices", "factory activity",
                            "services activity", "industrial production", "consumer confidence"))
            and contains_any(context, MACRO_ECONOMIES)
            and _matches(title, r"\b(?:grew|grows?|shrank|shrinks?|contracts?|expands?|rises?|rose|"
                         r"falls?|fell|slows?|accelerates?|beats?|misses?)\b")
            and _matches(title, r"\d[\d.,]*\s*(?:%|percent|per cent)")):
        return Assessment(8, "Publication d'une variation économique nationale", "MACRO")

    if (contains_any(title, ("economy", "growth"))
            and contains_any(title, ("consumer spending", "investment", "consumption"))
            and contains_any(title, MACRO_ECONOMIES)
            and _matches(title, r"\b(?:powers?|powered|drives?|drove|supports?|supported|boosts?|boosted)\b")
            and _matches(title, r"\b(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\b")):
        return Assessment(7, "Signal publié sur les moteurs de croissance nationale", "MACRO")

    if _matches(title, r"\b(?:us|u\.s\.|american)\b.{0,30}\b(?:adds?|added|loses?|lost)\b"
                      r".{0,20}\d[\d,]*\s+(?:new\s+)?jobs\b"):
        return Assessment(8, "Publication de l'emploi américain", "MACRO")

    if (_reference_bank_in_scope(title, context)
            and _matches(title, r"\b(?:signals?|rules? out|opens? (?:the )?door|pledges?)\b")
            and contains_any(title, ("rate cut", "rate cuts", "rate hike", "rate hikes",
                                     "tightening", "easing", "quantitative easing"))):
        return Assessment(7, "Orientation monétaire explicite", "MACRO")

    if (contains_any(title, ("opec", "opec+"))
            and contains_any(title, ("production", "output", "supply", "quota", "quotas"))
            and _matches(title, r"\b(?:agrees?|announces?|approves?|decides?|cuts?|raises?|"
                         r"increases?|reduces?|extends?|maintains?|restores?)\b")):
        return Assessment(9, "Décision de production de l'OPEP", "ENERGY")

    if supply_effect:
        return Assessment(9, "Interruption ou reprise d'un approvisionnement stratégique", "ENERGY")

    if is_major_company_penalty(original_title):
        return Assessment(7, "Sanction financière exceptionnelle sur une mégacapitalisation US", "EQUITIES")

    if (contains_any(title, ("ceasefire", "peace deal", "peace agreement"))
            and contains_any(context, COUNTRIES)
            and _matches(title, r"\b(?:agrees?|agreed|signs?|signed|reaches?|reached|"
                         r"accepts?|accepted|announces?|announced|begins?|began|"
                         r"takes? effect|collapses?|collapsed|ends?|ended)\b")):
        return Assessment(9, "Accord ou rupture de cessez-le-feu", "GEO")

    attack = _matches(title, r"\b(?:attacks?|attacked|strikes?|struck|hits?|hit|"
                      r"bombs?|bombed|bombing|invades?|invaded|"
                      r"declares? war|declared war)\b")
    # 'Launches an exhibition' n'est pas 'launches missiles'.
    attack = attack or _matches(
        title, r"\b(?:launches?|launched|fires?|fired)\s+"
               r"(?:(?:a|an|the|new|fresh|another|major|massive|full-scale|first|second|"
               r"wave|barrage|salvo|of|more|than|ballistic|cruise|hypersonic|long-range|\d+)\s+){0,8}"
               r"(?:missiles?|drones?|airstrikes?|air strikes?|attacks?|assault|offensive|invasion)\b"
    )
    # Le nom 'invasion' seul peut désigner un souvenir historique. Il faut
    # un acte militaire ou un début d'invasion explicitement annoncé.
    invasion_targets = "|".join(re.escape(country) for country in COUNTRIES)
    attack = attack or _matches(
        title, r"\b(?:begins?|began|starts?|started)\s+"
               r"(?:(?:a|an|the|new|fresh|full-scale|military)\s+){0,3}invasion\b"
               rf"|\binvasion(?:\s+of\s+(?:{invasion_targets}))?\s+"
               r"(?:begins?|began|starts?|started)\b"
    )
    strategic_attack = contains_any(title, STRATEGIC)
    interstate = sum(contains_any(title, group) for group in COUNTRY_GROUPS) >= 2
    major_action = contains_any(title, (
        "missile", "missiles", "airstrike", "airstrikes", "air strike", "air strikes",
        "invasion", "invades", "invaded", "declares war", "declared war",
    ))
    # 'hits' et 'strikes' seuls ne prouvent pas une attaque : une marée noire,
    # une vague ou une tempête peuvent aussi "frapper" un pétrolier.
    offensive = contains_any(title, (
        "attack", "attacks", "attacked", "bomb", "bombs", "bombed", "bombing",
        "invades", "invaded", "invasion", "declares war", "declared war",
        "missile", "missiles", "drone", "drones", "airstrike", "airstrikes",
        "air strike", "air strikes", "military strike", "military strikes",
    )) or _matches(title, r"\b(?:us|u\.s\.|iran|israel|russia|ukraine|nato|houthis?)"
                         r"\s+(?:(?:military|navy|forces)\s+)?strikes?\b")
    if (attack and offensive and ((strategic_attack and contains_any(context, COUNTRIES))
                    or (interstate and major_action))):
        return Assessment(9, "Attaque stratégique ou escalade militaire entre États", "GEO")

    # Mouvement explicite d'un marché de référence, pas la facture d'un ménage.
    if market_move:
        return Assessment(6, "Mouvement explicite d'un marché de référence", "MARKET")

    if title != original_title:
        return Assessment(0, "Contexte écarté : aucun mécanisme de marché dans l'annonce principale")
    return Assessment(0, "Aucun mécanisme de marché identifié : ni prix, décision économique ni résultat matériel")


def is_relevant(text, description=""):
    return assess_news(text, description).relevant
