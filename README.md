# META Screener — Multiple Edge Trading Area Stock Screener

Screens for high-probability entries where **multiple independent edges
converge** on one price area, based on J Law's Multiple Edge Trading Area
(META) framework — instead of single-reason entries (one candle, one MA, one
news tip).

## Edges detected

| Edge | What it tests |
|---|---|
| **Trend** | Strong uptrend: green-candle dominance, EMA10>20>50 stack, HH/HL structure, +8% 20d momentum, price not touching EMA50 |
| **AtSupport** | Price sitting on / wicking into a clustered pivot support zone (zones, not lines) |
| **Weekly** | Higher-timeframe alignment: weekly close > EMA10 > EMA30, rising |
| **LowVolPB** | Healthy pullback: shallow (<15%) decline from recent high on contracting volume, <62% retrace of up-leg |
| **VolFuel** | Volume is fuel: up-day volume > down-day volume |
| **Breakout** | Close crossed above a zone in last 15 bars on ≥1.3× 50d-avg volume |
| **Retest** | Price returned to the flipped zone (old resistance = new support) |
| **RelStr** | Relative strength vs benchmark (`^HSI`): stock outperforms over 2+ of 3 lookback windows, OR market-down/stock-up divergence (J Law 照妖鏡) |

Each edge has a weight (`config.EDGE_WEIGHTS`); the **META score** sums the
converging edges. A **META setup** requires score ≥ 5 AND genuine convergence
(e.g. `META PULLBACK` = Trend + AtSupport + Weekly + LowVolPB/Retest).

## Setup types

- **META PULLBACK** — strong trend, price pulled back into a support zone on
  low volume, weekly aligned. Stop suggested below zone (half-ATR buffer).
- **META RETEST** — volume breakout happened, price retesting flipped zone.
- **BREAKOUT** — fresh volume-confirmed zone breakout.
- **TRENDING / TREND PULLBACK** — watchlist only.
- **RS LEADER** — strong relative strength vs benchmark (J Law: 大盤跌佢升＝照妖鏡)
  but NOT full META convergence. Score ≥ `RS_LEADER_MIN_SCORE` (4.5) + RelStr active.
  Watchlist: high-probability leaders worth stalking for a pullback entry.

## Usage

```bash
python main.py                          # full HK universe -> console + dashboard
python main.py --market us              # full US universe (benchmark = ^IXIC)
python main.py --symbols 0700.HK,AAPL   # custom tickers (any Yahoo symbol)
python main.py --market us --symbols NVDA,AMD,PLTR   # US names, US benchmark
python main.py --refresh                # bypass 12h cache
python main.py --min-score 4 --top 20   # filter rows, more charts
python main.py --no-dashboard           # console only
```

## Markets

The same edge engine screens both markets; only the universe, RS benchmark,
liquidity filter and quote currency differ (see `MARKETS` in `config.py`):

| Market | Universe | RS benchmark | Min turnover | Currency |
|---|---|---|---|---|
| `hk` (default) | `HK_UNIVERSE` (84 large caps) | `^HSI` | HK$50M | HKD |
| `us` | `US_UNIVERSE` (~52 large caps) | `^IXIC` (Nasdaq) | US$200M | USD |
| `nasdaq` | **full Nasdaq** (~3,600 common stocks) | `^IXIC` | US$200M | USD |

Pick with `--market hk|us|nasdaq`. When `--symbols` is given, the benchmark/currency
still follow `--market` (so screen US tickers with `--market us`).

**Full Nasdaq scan** (`--market nasdaq`): pulls the official Nasdaq symbol
directory from `nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt` (cached to
`cache/nasdaq_universe.json`, refreshed when older than 1 day; ETFs / warrants /
units / rights / preferreds are skipped). Then yfinance downloads every symbol
and the liquidity filter (`MIN_AVG_TURNOVER`) screens out thin names — on the
first full run ~3,600 names collapse to ~350 tradable ones. **First run is slow**
(downloading thousands of symbols); subsequent runs reuse the 12h cache.

Output: console ranking + `reports/meta_dashboard_<market>_<timestamp>.html`
(sortable table, candlestick charts with S/R zones + lines, EMAs, volume, RSI,
MACD, stop line, divergence markers) + `reports/meta_summary_<market>_<timestamp>.md`.

## Data

Yahoo Finance via `yfinance` (batch download), cached per symbol as CSV in
`cache/` (12h max age). Universes in `config.py`: `HK_UNIVERSE` (~84 curated HK
large caps) + `US_UNIVERSE` (~52 US large caps) + **full Nasdaq** (fetched live
from `nasdaqtrader.com`, cached to `cache/nasdaq_universe.json`). Liquidity
filter: avg daily turnover ≥ HK$50M (HK) / US$200M (US & nasdaq) — see `MARKETS`.

## Files

- `config.py` — universe + every threshold (tune edges here)
- `data.py` — fetch/cache layer
- `edges.py` — the 9 edge detectors (trend / support / htf / pullback / volume /
  breakout / retest / relative-strength / RSI-MACD divergence) + pivot/zone engine
- `screener.py` — scoring, setup classification, ranking
- `dashboard.py` — HTML report generator (plotly, dark theme)
- `main.py` — CLI
- `daily_scan.py` — scheduled runner: scans selected markets, saves a dashboard
  per market + a markdown summary + one PNG chart per signal stock, prints a
  META/RS summary, optionally **emails** (reads `SMTP_*`/`EMAIL_TO`) and/or
  **pushes to Telegram** (reads `TG_BOT_TOKEN`/`TG_CHAT_ID`) them.

## Telegram push (optional)

Set `TG_BOT_TOKEN` + `TG_CHAT_ID` in `config.py` (create a bot via
[@BotFather](https://t.me/BotFather), get `TG_CHAT_ID` from
[@RawDataBot](https://t.me/RawDataBot) or `getUpdates`). With both set,
`daily_scan.py` sends, per market:

1. the markdown summary split into ≤3900-char text chunks, **and**
2. one PNG chart per META / RS LEADER signal stock (rendered via `kaleido`).

Leave either blank to skip Telegram. Flags `--no-email` / `--no-telegram` skip
each channel.

## Daily scheduling (Windows Task Scheduler)

`daily_scan.py` reuses the same engine. Run it on a schedule so you get fresh
META setups + RS leaders every morning without manual runs.

1. Configure email in `config.py` (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`,
   `EMAIL_TO`). For Gmail use an **app password**, not your login password.
   Leave `SMTP_HOST` empty to skip email — dashboards are still saved locally.
2. Create the task in **Admin PowerShell**:

```powershell
$py = "$env:USERPROFILE\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$script = "C:\Users\lauki\WorkBuddy\2026-08-24-22-47-53\meta_screener\daily_scan.py"
# HK close run (16:35 HKT) — scans both markets
schtasks /Create /TN "META Screener Daily" /TR "$py $script --market hk,us" `
  /SC DAILY /ST 16:35 /RL HIGHEST
# optional US-only run after US close (~04:35 HKT = 16:35 ET prev day)
schtasks /Create /TN "META Screener US" /TR "$py $script --market us" `
  /SC DAILY /ST 04:35 /RL HIGHEST
# optional full-Nasdaq sweep (slow first run; best off-peak, e.g. weekend)
schtasks /Create /TN "META Screener NASDAQ" /TR "$py $script --market nasdaq" `
  /SC WEEKLY /D SAT /ST 06:00 /RL HIGHEST
```
3. Test once: `& $py $script --market hk,us --no-email`
4. Verify: `schtasks /Query /TN "META Screener Daily"`

*Educational screening tool — not investment advice.*
