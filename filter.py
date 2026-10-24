"""Sélection prudente d'événements macro, énergie et géopolitiques.

Un sujet sensible ne suffit pas : il faut une annonce ou un mouvement concret.
Le titre reste déterminant ; le résumé ne peut pas sauver un témoignage ou
un avertissement général. Règles destinées aux sources anglophones du bot.
"""

import html
import re
from dataclasses import dataclass
from functools import lru_cache


FILTER_VERSION = "pertinence-v2.2"


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
    r"could|might|may (?:cut|hold|raise|close|attack|impose|reopen|resume|halt|increase|reduce)|"
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
)
US_MEGACAPS = ("apple", "microsoft", "nvidia", "alphabet", "google", "amazon", "meta", "tesla")


def _event_clause(title):
    """Évaluer l'annonce avant son contexte causal, sans supprimer un 'if'."""
    if re.match(r"^(?:after|as|amid|despite|following|while|although)\b", title) and "," in title:
        title = title.split(",", 1)[1].strip()
    return re.split(
        r"\b(?:after|as|amid|while|despite|but|although|following|because|"
        r"on (?:hopes|expectations|fears|reports))\b", title, maxsplit=1
    )[0].strip(" ,;:-")


def is_trade_decision(title, description=""):
    context = normalize_text(f"{title} {description}")
    title = _event_clause(normalize_text(title))
    if EDITORIAL.search(title):
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
        and _matches(action_text, r"\b(?:imposes?|imposed|announces?|announced|approves?|"
                     r"approved|enacts?|enacted|lifts?|lifted|removes?|removed|"
                     r"suspends?|suspended|raises?|raised|increases?|increased|"
                     r"cuts?|extends?|extended|ends?|ended|scraps?|scrapped|"
                     r"slashes?|slashed|reduces?|reduced|eases?|eased|tightens?|tightened|"
                     r"doubles?|doubled|introduces?|introduced|takes? effect|comes? into force)\b")
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
    return contains_any(text, PERSONAL_STORIES) or bool(PERSONAL_PATTERN.search(text))


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
    benchmarks = ("oil prices", "crude prices", "brent", "wti", "gold", "dollar",
                  "treasury yields", "bond yields", "wall street", "nasdaq", "s&p 500",
                  "natural gas prices", "stock markets", "global stocks", "us stocks",
                  "u.s. stocks", "us stock futures", "dow jones", "dow", "s&p500")
    benchmark_leads = any(
        match and match.start() <= 15
        for match in (_term_pattern(term).search(title) for term in benchmarks)
    )
    return benchmark_leads and _matches(
        title, r"\b(?:surges?|surged|plunges?|plunged|soars?|soared|tumbles?|tumbled|"
               r"jumps?|jumped|slumps?|slumped|rallies|rallied|slides?|slid|rises?|rose|"
               r"falls?|fell|hits?|hit|drops?|dropped|sinks?|sank|rebounds?|rebounded|"
               r"gains?|gained|weakens?|weakened|strengthens?|strengthened)\b"
    )


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
    if EDITORIAL.search(title):
        return Assessment(0, "Analyse, question ou scénario hypothétique")

    supply_effect = _supply_effect(title)
    market_move = _market_move(title)
    local_incident = contains_any(title, (
        "oil spill", "oil spills", "oil slick", "oil slicks", "collision",
        "tanker accident", "pollution",
    ))
    if local_incident and not (supply_effect or market_move):
        return Assessment(0, "Pollution ou accident local sans effet explicite sur les flux ou les marchés")

    # Décision de taux, y compris maintien : ne pas exiger des mots 'hawkish'.
    rate_action = _matches(title, r"\b(?:cuts?|raises?|raised|hikes?|hiked|holds?|held|keeps?|"
                           r"kept|leaves?|left|lowers?|lowered|maintains?|maintained|"
                           r"reduces?|reduced|increases?|increased|slashes?|slashed|"
                           r"cutting|raising|unchanged)\b")
    rate_action = rate_action or _matches(
        title, r"\b(?:announces?|announced|approves?|approved|delivers?|delivered)\b"
               r".{0,30}\brate (?:cuts?|hikes?|increase|reduction)\b"
    )
    if (contains_any(context, CENTRAL_BANKS) and rate_action
            and contains_any(title, ("rate", "rates", "interest rate", "borrowing costs"))):
        return Assessment(9, "Décision de politique monétaire")

    if (contains_any(title, INDICATORS)
            and _matches(title, r"\d[\d.,]*\s*(?:%|percent|per cent)|"
                         r"\b(?:rises?|rose|falls?|fell|slows?|slowed|cools?|cooled|eases?|eased|"
                         r"accelerates?|accelerated|jumps?|jumped|drops?|dropped|contracts?|"
                         r"expands?|beats?|misses?|higher|lower|highest|lowest|unchanged|released)\b")):
        if contains_any(title, LOCAL_MACRO):
            return Assessment(0, "Statistique économique locale hors périmètre macro")
        if not (contains_any(context, MACRO_ECONOMIES) or contains_any(title, US_INDICATORS)):
            return Assessment(0, "Portée nationale ou économie de référence non identifiée")
        return Assessment(8, "Publication ou variation d'un indicateur macroéconomique")

    if _matches(title, r"\b(?:us|u\.s\.|american)\b.{0,30}\b(?:adds?|added|loses?|lost)\b"
                      r".{0,20}\d[\d,]*\s+(?:new\s+)?jobs\b"):
        return Assessment(8, "Publication de l'emploi américain")

    if (contains_any(context, CENTRAL_BANKS)
            and _matches(title, r"\b(?:signals?|rules? out|opens? (?:the )?door|pledges?)\b")
            and contains_any(title, ("rate cut", "rate cuts", "rate hike", "rate hikes",
                                     "tightening", "easing", "quantitative easing"))):
        return Assessment(7, "Orientation monétaire explicite")

    if (contains_any(title, ("opec", "opec+"))
            and contains_any(title, ("production", "output", "supply", "quota", "quotas"))
            and _matches(title, r"\b(?:agrees?|announces?|approves?|decides?|cuts?|raises?|"
                         r"increases?|reduces?|extends?|maintains?|restores?)\b")):
        return Assessment(9, "Décision de production de l'OPEP")

    if supply_effect:
        return Assessment(9, "Interruption ou reprise d'un approvisionnement stratégique")

    if is_trade_decision(title, context):
        return Assessment(8, "Décision de sanctions ou de politique commerciale")

    if is_major_company_penalty(original_title):
        return Assessment(7, "Sanction financière exceptionnelle sur une mégacapitalisation US")

    if (contains_any(title, ("ceasefire", "peace deal", "peace agreement"))
            and contains_any(context, COUNTRIES)
            and _matches(title, r"\b(?:agrees?|agreed|signs?|signed|reaches?|reached|"
                         r"accepts?|accepted|announces?|announced|begins?|began|"
                         r"takes? effect|collapses?|collapsed|ends?|ended)\b")):
        return Assessment(9, "Accord ou rupture de cessez-le-feu")

    attack = _matches(title, r"\b(?:attacks?|attacked|strikes?|struck|hits?|hit|"
                      r"bombs?|bombed|bombing|invades?|invaded|invasion|launches?|launched|"
                      r"declares? war|declared war)\b")
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
        return Assessment(9, "Attaque stratégique ou escalade militaire entre États")

    # Mouvement explicite d'un marché de référence, pas la facture d'un ménage.
    if market_move:
        return Assessment(6, "Mouvement explicite d'un marché de référence")

    return Assessment(0, "Aucun événement concret suffisamment pertinent identifié")


def is_relevant(text, description=""):
    return assess_news(text, description).relevant
