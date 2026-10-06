"""Configuration for the META (Multiple Edge Trading Area) Screener.

Framework based on J Law's teaching: only trade where MULTIPLE independent
edges converge (strong trend + support/resistance zone + volume behavior +
higher-timeframe alignment), instead of single-reason entries.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
REPORT_DIR = os.path.join(BASE_DIR, "reports")


def _load_dotenv(path=os.path.join(BASE_DIR, ".env")):
    """Load KEY=VALUE pairs from a local .env into os.environ (no deps).

    Keeps real secrets (Telegram token, chat id, SMTP creds) OUT of config.py
    so they are never committed to the public GitHub repo. .env is gitignored.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_dotenv()

# ---------------------------------------------------------------- Data
FETCH_PERIOD = "2y"          # daily history to fetch & cache
CACHE_MAX_AGE_HOURS = 12     # refetch cached symbol if older than this

# ---------------------------------------------------------------- Universe
# Curated HK large-cap universe (extends the old stock_screener list).
HK_UNIVERSE = {
    # --- from original screener (38) ---
    "0700.HK": "Tencent",
    "9988.HK": "Alibaba",
    "0939.HK": "CCB",
    "1299.HK": "AIA",
    "0941.HK": "China Mobile",
    "0388.HK": "HKEX",
    "0005.HK": "HSBC",
    "0883.HK": "CNOOC",
    "1398.HK": "ICBC",
    "2318.HK": "Ping An",
    "3988.HK": "Bank of China",
    "0001.HK": "CK Hutchison",
    "0011.HK": "Hang Seng Bank",
    "0016.HK": "Sun Hung Kai Prop",
    "0002.HK": "CLP Holdings",
    "0386.HK": "Sinopec",
    "0857.HK": "PetroChina",
    "0288.HK": "WH Group",
    "0289.HK": "Zijin Mining",
    "0688.HK": "China Overseas Land",
    "0762.HK": "China Unicom",
    "0823.HK": "Link REIT",
    "1038.HK": "CK Infrastructure",
    "1093.HK": "CSPC Pharma",
    "1109.HK": "China Res Land",
    "1113.HK": "CK Asset",
    "1810.HK": "Xiaomi",
    "1928.HK": "Sands China",
    "2020.HK": "ANTA Sports",
    "2269.HK": "WuXi Biologics",
    "2313.HK": "Shenzhou Intl",
    "2382.HK": "Sunny Optical",
    "2628.HK": "China Life",
    "3328.HK": "Bank of Comm",
    "3690.HK": "Meituan",
    "9618.HK": "JD.com",
    "9633.HK": "Nongfu Spring",
    "9999.HK": "NetEase",
    # --- extended large caps ---
    "0003.HK": "HK & China Gas",
    "0006.HK": "Power Assets",
    "0012.HK": "Henderson Land",
    "0017.HK": "New World Dev",
    "0027.HK": "Galaxy Ent",
    "0066.HK": "MTR Corp",
    "0101.HK": "Hang Lung Prop",
    "0175.HK": "Geely Auto",
    "0267.HK": "CITIC",
    "0291.HK": "China Res Beer",
    "0322.HK": "Tingyi",
    "0669.HK": "Techtronic",
    "0836.HK": "China Res Power",
    "0868.HK": "Xinyi Glass",
    "0960.HK": "Longfor",
    "1044.HK": "Hengan Intl",
    "1088.HK": "China Shenhua",
    "1114.HK": "Brilliance China",
    "1177.HK": "Sino Biopharm",
    "1211.HK": "BYD",
    "1919.HK": "COSCO Shipping",
    "1997.HK": "Wharf",
    "2015.HK": "Li Auto",
    "2319.HK": "China Mengniu",
    "2331.HK": "Li Ning",
    "2388.HK": "BOC Hong Kong",
    "2600.HK": "Chalco",
    "2688.HK": "ENN Energy",
    "6030.HK": "CITIC Sec",
    "6160.HK": "Budweiser APAC",
    "6690.HK": "Haier Smart Home",
    "6862.HK": "Haidilao",
    "9888.HK": "Baidu",
    "9866.HK": "NIO",
    "9868.HK": "XPeng",
    "9961.HK": "Trip.com",
}

# ---------------------------------------------------------------- Universe (US)
# Curated US large-cap universe (growth + megacap). Shares the same edge engine
# as HK_UNIVERSE; only benchmark / liquidity / currency differ (see MARKETS).
US_UNIVERSE = {
    # megacap core
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "AMZN": "Amazon",
    "GOOGL": "Alphabet",
    "META": "Meta Platforms",
    "TSLA": "Tesla",
    "AVGO": "Broadcom",
    "LLY": "Eli Lilly",
    "BRK-B": "Berkshire Hathaway",
    "JPM": "JPMorgan",
    "V": "Visa",
    "UNH": "UnitedHealth",
    "XOM": "Exxon Mobil",
    "JNJ": "Johnson & Johnson",
    "WMT": "Walmart",
    "MA": "Mastercard",
    "PG": "Procter & Gamble",
    "HD": "Home Depot",
    "COST": "Costco",
    "BAC": "Bank of America",
    "KO": "Coca-Cola",
    "PEP": "PepsiCo",
    "T": "AT&T",
    "WFC": "Wells Fargo",
    "MS": "Morgan Stanley",
    "GS": "Goldman Sachs",
    "C": "Citigroup",
    # growth / momentum (names J Law trades)
    "NFLX": "Netflix",
    "AMD": "AMD",
    "CRM": "Salesforce",
    "ORCL": "Oracle",
    "ADBE": "Adobe",
    "PLTR": "Palantir",
    "COIN": "Coinbase",
    "SMCI": "Super Micro",
    "APP": "Applovin",
    "SHOP": "Shopify",
    "PANW": "Palo Alto Networks",
    "CRWD": "CrowdStrike",
    "NET": "Cloudflare",
    "SNOW": "Snowflake",
    "ZS": "Zscaler",
    "MDB": "MongoDB",
    "FSLR": "First Solar",
    "ROKU": "Roku",
    "INTU": "Intuit",
    "NOW": "ServiceNow",
    "ABNB": "Airbnb",
    "UBER": "Uber",
    "QCOM": "Qualcomm",
    "TXN": "Texas Instruments",
    "CSCO": "Cisco",
    "INTC": "Intel",
    "BKNG": "Booking",
    "TSM": "TSMC ADR",
    "ARM": "Arm Holdings",
    "ASML": "ASML",
}

# ---------------------------------------------------------------- Filters
MIN_AVG_TURNOVER = 30_000_000   # default (HK) avg daily turnover (close*volume), 6m
MIN_BARS = 120                  # minimum trading days of data required

# ---------------------------------------------------------------- Edge tuning
# Edge 1: strong trend
TREND_LOOKBACK = 20             # bars for candle-dominance / momentum
GREEN_RATIO_MIN = 0.55          # fraction of bullish candles
RET20_MIN = 0.08                # 20d return threshold (8%)
TREND_MIN_CHECKS = 3            # of 5 checks needed for trend edge

# Edge 2: volume behaviour
UPDOWN_VOL_RATIO = 1.15         # up-day vol vs down-day vol (fuel test)

# Edge 3: healthy low-volume pullback
PULLBACK_MAX_DEPTH = 0.15       # max decline from recent swing high
PULLBACK_WINDOW = 15            # bars to search for the swing high
PULLBACK_MAX_RETRACE = 0.62     # of the prior up-leg (fib-ish 0.618)

# Edge 4: support/resistance zones
ZONE_LOOKBACK = 250             # bars used to build zones (~1 year)
ZONE_TOL = 0.02                 # cluster tolerance (2% of price)
ZONE_MIN_TOUCHES = 2            # pivots needed to form a zone
NEAR_SUPPORT_PCT = 0.025        # "near zone" if within 2.5% above it

# Edge 5: higher timeframe
HTF_EMA_FAST = 10               # weekly EMA periods
HTF_EMA_SLOW = 30

# Edge 6/7: breakout & retest
BREAKOUT_LOOKBACK = 15          # bars to search for a zone cross
BREAKOUT_VOL_MULT = 1.3         # volume vs 50d avg on breakout day
RETEST_BAND = 0.03              # price within +/-3% of flipped zone

# Edge 8: relative strength vs benchmark (J Law: 大盤跌佢升 = 照妖鏡)
RS_WINDOWS = [20, 60, 120]      # lookback windows (bars) for RS comparison
RS_MIN_OUTPERFORM = 2           # of 3 windows the stock must beat benchmark
RS_LEADER_MIN_SCORE = 4.5      # RS LEADER watchlist: strong RS but not full META convergence

# Edge 9: RSI / MACD divergence (momentum deceleration)
DIVERGENCE_LOOKBACK = 180       # bars scanned for swing pivots
DIVERGENCE_MIN_BARS = 10        # min trading-day gap between the two pivots compared

# ---------------------------------------------------------------- Markets
# HK + US share the SAME edge engine; only universe / benchmark / liquidity
# filter / currency differ. Resolved per-run in main.py via --market. Defaults
# below keep the original HK behaviour intact when --market is omitted.
MARKETS = {
    "hk": {
        "universe": HK_UNIVERSE,
        "benchmark": "^HSI",        # Hang Seng Index
        "min_turnover": 30_000_000,
        "currency": "HKD",
    },
    "us": {
        "universe": US_UNIVERSE,
        "benchmark": "^IXIC",       # Nasdaq Composite (J Law growth leaders)
        "min_turnover": 200_000_000,
        "currency": "USD",
    },
    "nasdaq": {
        "universe_source": "nasdaq",  # dynamic via data.fetch_nasdaq_universe()
        "benchmark": "^IXIC",          # full NASDAQ listed vs Nasdaq Composite
        "min_turnover": 200_000_000,  # same liquidity bar as `us` (tune down for small caps)
        "currency": "USD",
    },
}
DEFAULT_MARKET = "hk"
RS_BENCHMARK = MARKETS[DEFAULT_MARKET]["benchmark"]
CURRENCY = MARKETS[DEFAULT_MARKET]["currency"]

# ---------------------------------------------------------------- Scoring
EDGE_WEIGHTS = {
    "trend": 2.0,      # scaled by trend strength (0-5 checks)
    "support": 2.0,    # price sitting on a support zone
    "htf": 1.0,        # weekly timeframe aligned
    "pullback": 1.0,   # healthy low-volume pullback
    "volume": 0.5,     # up-volume > down-volume
    "breakout": 1.5,   # volume-confirmed zone breakout
    "retest": 1.5,     # retesting flipped zone after breakout
    "rs": 1.5,         # relative strength vs benchmark (照妖鏡)
    "divergence": 1.0, # RSI/MACD bullish divergence (momentum reversal edge)
}
MAX_SCORE = sum(EDGE_WEIGHTS.values())

# META setup requires convergence of independent edges
META_SETUP_MIN_SCORE = 5.0

# ---------------------------------------------------------------- Report
DASHBOARD_TOP_N = 14             # charts to embed in dashboard
CHART_BARS = 130                 # candles per chart

# ---------------------------------------------------------------- Email (optional)
# Fill to enable daily report delivery via daily_scan.py. For Gmail use an
# APP PASSWORD, not your login password. Leave SMTP_HOST empty to skip email
# (dashboards are still saved locally).
SMTP_HOST = ""               # e.g. "smtp.gmail.com"
SMTP_PORT = 465              # SSL port
SMTP_USER = ""               # sender login (your email)
SMTP_PASS = ""               # app password / auth token
EMAIL_TO = []                # list of recipient addresses
EMAIL_FROM_NAME = "META Screener"

# ---------------------------------------------------------------- Telegram (optional)
# Secrets are read from environment / a local .env file (gitignored) so they are
# NEVER committed to the public repo. Put them in .env like:
#     TG_BOT_TOKEN=123456789:AAE...longstring
#     TG_CHAT_ID=-1001234567890        # channel, or 987654321 for your user id
# If TG_CHAT_ID is empty, daily_scan.py auto-discovers it from the latest message
# you sent the bot (so just message the bot once, then run). Leave both empty to
# skip Telegram push. Get BOT_TOKEN from @BotFather; your chat id from @userinfobot.
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
