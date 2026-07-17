"""
Mundane / financial astrology rulership tables.

This encodes classical planet -> sector associations used in traditional
financial astrology. It is a DECLARED RULE SET, not a scientifically
validated model. The backtester (backtest.py) measures how often each rule
has historically lined up with actual sector price moves, and weekly_review.py
adjusts each rule's weight over time based on real hit-rate -- so the system
is honest about which rules are working and which aren't, rather than
treating all rules as equally reliable.
"""

# Tradable proxies (liquid ETFs) for each sector, on NYSE unless noted.
SECTOR_TICKERS = {
    "Energy": "XLE",
    "Financials": "XLF",
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Materials_Mining": "XLB",
    "Consumer_Discretionary": "XLY",
    "Consumer_Staples": "XLP",
    "Utilities": "XLU",
    "Real_Estate": "XLRE",
    "Communication_Media": "XLC",
    "Gold": "GLD",
    "Silver": "SLV",
    "Canada_Broad": "XIU.TO",   # iShares S&P/TSX 60, Toronto
    "US_Broad": "SPY",
}

# Classical sign rulerships (traditional, pre-outer-planet-discovery scheme,
# which is what most financial/mundane astrology practice still uses)
SIGN_RULER = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

# Which sectors each planet governs, and the DIRECTION its placement/strength
# tends to favor, per classical financial-astrology convention. Weight is a
# starting prior (0-1); weekly_review.py updates these based on real outcomes.
PLANET_SECTOR_RULES = {
    "Sun":     {"sectors": ["Energy", "US_Broad", "Gold"], "weight": 0.5},
    "Moon":    {"sectors": ["Consumer_Staples", "Real_Estate"], "weight": 0.5},
    "Mercury": {"sectors": ["Technology", "Communication_Media", "Financials"], "weight": 0.5},
    "Venus":   {"sectors": ["Consumer_Discretionary", "Real_Estate"], "weight": 0.5},
    "Mars":    {"sectors": ["Materials_Mining", "Energy", "Industrials"], "weight": 0.5},
    "Jupiter": {"sectors": ["Financials", "Healthcare", "US_Broad"], "weight": 0.5},
    "Saturn":  {"sectors": ["Utilities", "Materials_Mining", "Industrials"], "weight": 0.5},
    "Rahu":    {"sectors": ["Technology", "Canada_Broad"], "weight": 0.4},
    "Ketu":    {"sectors": ["Healthcare", "Gold"], "weight": 0.4},
}

# Sign a planet is "exalted" in (traditionally strong/bullish for its sectors)
# and "debilitated" in (traditionally weak/bearish for its sectors).
EXALTATION = {
    "Sun": "Aries", "Moon": "Taurus", "Mercury": "Virgo", "Venus": "Pisces",
    "Mars": "Capricorn", "Jupiter": "Cancer", "Saturn": "Libra",
}
DEBILITATION = {
    "Sun": "Libra", "Moon": "Scorpio", "Mercury": "Pisces", "Venus": "Virgo",
    "Mars": "Cancer", "Jupiter": "Capricorn", "Saturn": "Aries",
}

# Retrograde effect: classical convention treats retrograde as a signal of
# reversal / instability in the planet's sectors, not flatly "bearish" --
# it raises expected volatility and slightly favors reversal-of-prior-trend.
RETROGRADE_VOLATILITY_BOOST = 0.15

# Orb (degrees) within which two planets are considered in aspect
ASPECT_ORB = 6.0
# Aspect angles considered and their classical tone
ASPECTS = {
    0:   {"name": "Conjunction", "tone": "amplify"},
    90:  {"name": "Square", "tone": "bearish"},
    120: {"name": "Trine", "tone": "bullish"},
    180: {"name": "Opposition", "tone": "bearish"},
}
