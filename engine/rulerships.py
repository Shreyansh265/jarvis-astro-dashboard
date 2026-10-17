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
    "Canada_Broad": "EWC",      # iShares MSCI Canada ETF, NYSE-Arca (Twelve
                                # Data's free tier blocks TSX-listed symbols
                                # like XIU.TO -- confirmed via live 403 --
                                # EWC gives the same Canada exposure on NYSE)
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

# Individual stock picks within each sector, for the Astro Stocks tab and
# the market-watch gainers/losers scan. Curated, liquid, well-known names --
# only for sectors that actually get a signal (i.e. appear in
# PLANET_SECTOR_RULES above). Silver has no planetary rule and never
# signals, and US_Broad (the whole market) has no single meaningful stock
# pick, so both are intentionally left out here.
SECTOR_TOP_STOCKS = {
    "Energy": ["XOM", "CVX", "COP"],
    "Financials": ["JPM", "BAC", "GS"],
    "Technology": ["AAPL", "MSFT", "NVDA"],
    "Healthcare": ["UNH", "JNJ", "LLY"],
    "Industrials": ["CAT", "BA", "HON"],
    "Materials_Mining": ["LIN", "FCX", "NEM"],
    "Consumer_Discretionary": ["AMZN", "HD", "MCD"],
    "Consumer_Staples": ["PG", "KO", "PEP"],
    "Utilities": ["NEE", "DUK", "SO"],
    "Real_Estate": ["AMT", "PLD", "EQIX"],
    "Communication_Media": ["GOOGL", "META", "NFLX"],
    "Gold": ["AEM", "FNV", "AU"],   # NOT "GOLD" -- on Twelve Data's free
                                    # tier that symbol resolves to an
                                    # unrelated micro-cap ("Gold.com, Inc."),
                                    # not Barrick; confirmed live.
    "Canada_Broad": ["RY", "TD", "SHOP"],
}

# The stocks a user can pick inside a sector on the This Week's Signals tab
# (names only, mirrored to the sector_universe table by engine/forecast.py).
# Deliberately SEPARATE from SECTOR_TOP_STOCKS above: that dict drives
# stock_picks.py (suggests every listed ticker in a signaled sector) and
# market_watch.py (prices every listed ticker daily), so enlarging it would
# multiply quotes and Twelve Data credits. A stock chosen from here simply
# inherits its sector's forecast -- no per-stock astrology exists, and the UI
# says so.
SECTOR_STOCK_UNIVERSE = {
    "Energy": [("XOM", "Exxon Mobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips"),
               ("EOG", "EOG Resources"), ("SLB", "Schlumberger"), ("OXY", "Occidental Petroleum"),
               ("MPC", "Marathon Petroleum"), ("PSX", "Phillips 66")],
    "Financials": [("JPM", "JPMorgan Chase"), ("BAC", "Bank of America"), ("GS", "Goldman Sachs"),
                   ("MS", "Morgan Stanley"), ("WFC", "Wells Fargo"), ("C", "Citigroup"),
                   ("BLK", "BlackRock"), ("SCHW", "Charles Schwab")],
    "Technology": [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"),
                   ("AVGO", "Broadcom"), ("ORCL", "Oracle"), ("CRM", "Salesforce"),
                   ("AMD", "AMD"), ("ADBE", "Adobe")],
    "Healthcare": [("UNH", "UnitedHealth"), ("JNJ", "Johnson & Johnson"), ("LLY", "Eli Lilly"),
                   ("PFE", "Pfizer"), ("ABBV", "AbbVie"), ("MRK", "Merck"),
                   ("TMO", "Thermo Fisher"), ("ABT", "Abbott Laboratories")],
    "Industrials": [("CAT", "Caterpillar"), ("BA", "Boeing"), ("HON", "Honeywell"),
                    ("GE", "GE Aerospace"), ("UPS", "UPS"), ("DE", "Deere"),
                    ("LMT", "Lockheed Martin"), ("RTX", "RTX")],
    "Materials_Mining": [("LIN", "Linde"), ("FCX", "Freeport-McMoRan"), ("NEM", "Newmont"),
                         ("SHW", "Sherwin-Williams"), ("APD", "Air Products"), ("NUE", "Nucor"),
                         ("DOW", "Dow"), ("ECL", "Ecolab")],
    "Consumer_Discretionary": [("AMZN", "Amazon"), ("HD", "Home Depot"), ("MCD", "McDonald's"),
                               ("TSLA", "Tesla"), ("NKE", "Nike"), ("SBUX", "Starbucks"),
                               ("LOW", "Lowe's"), ("BKNG", "Booking Holdings")],
    "Consumer_Staples": [("PG", "Procter & Gamble"), ("KO", "Coca-Cola"), ("PEP", "PepsiCo"),
                         ("WMT", "Walmart"), ("COST", "Costco"), ("PM", "Philip Morris"),
                         ("CL", "Colgate-Palmolive"), ("MDLZ", "Mondelez")],
    "Utilities": [("NEE", "NextEra Energy"), ("DUK", "Duke Energy"), ("SO", "Southern Company"),
                  ("D", "Dominion Energy"), ("AEP", "American Electric Power"), ("EXC", "Exelon"),
                  ("SRE", "Sempra"), ("XEL", "Xcel Energy")],
    "Real_Estate": [("AMT", "American Tower"), ("PLD", "Prologis"), ("EQIX", "Equinix"),
                    ("SPG", "Simon Property"), ("O", "Realty Income"), ("PSA", "Public Storage"),
                    ("CCI", "Crown Castle"), ("WELL", "Welltower")],
    "Communication_Media": [("GOOGL", "Alphabet (Google)"), ("META", "Meta Platforms"), ("NFLX", "Netflix"),
                            ("DIS", "Disney"), ("CMCSA", "Comcast"), ("T", "AT&T"),
                            ("VZ", "Verizon"), ("TMUS", "T-Mobile US")],
    "Gold": [("AEM", "Agnico Eagle"), ("FNV", "Franco-Nevada"), ("AU", "AngloGold Ashanti"),
             ("KGC", "Kinross Gold"), ("WPM", "Wheaton Precious Metals"), ("GFI", "Gold Fields"),
             ("HMY", "Harmony Gold"), ("NEM", "Newmont")],
    "Silver": [("WPM", "Wheaton Precious Metals"), ("PAAS", "Pan American Silver"), ("AG", "First Majestic Silver"),
               ("HL", "Hecla Mining"), ("CDE", "Coeur Mining"), ("MAG", "MAG Silver")],
    "Canada_Broad": [("RY", "Royal Bank of Canada"), ("TD", "TD Bank"), ("SHOP", "Shopify"),
                     ("ENB", "Enbridge"), ("BNS", "Scotiabank"), ("BMO", "Bank of Montreal"),
                     ("CNQ", "Canadian Natural Resources"), ("CP", "Canadian Pacific Kansas City")],
    "US_Broad": [("SPY", "S&P 500 ETF"), ("QQQ", "Nasdaq-100 ETF"), ("DIA", "Dow Jones ETF"),
                 ("IWM", "Russell 2000 ETF")],
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
