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

Each edge has a weight (`config.EDGE_WEIGHTS`); the **META score** sums the
converging edges. A **META setup** requires score ≥ 5 AND genuine convergence
(e.g. `META PULLBACK` = Trend + AtSupport + Weekly + LowVolPB/Retest).

## Setup types

- **META PULLBACK** — strong trend, price pulled back into a support zone on
  low volume, weekly aligned. Stop suggested below zone (half-ATR buffer).
- **META RETEST** — volume breakout happened, price retesting flipped zone.
- **BREAKOUT** — fresh volume-confirmed zone breakout.
- **TRENDING / TREND PULLBACK** — watchlist only.

## Usage

```bash
python main.py                          # full HK universe -> console + dashboard
python main.py --symbols 0700.HK,AAPL   # custom tickers (any Yahoo symbol)
python main.py --refresh                # bypass 12h cache
python main.py --min-score 4 --top 20   # filter rows, more charts
python main.py --no-dashboard           # console only
```

Output: console ranking + `reports/meta_dashboard_<timestamp>.html`
(sortable table, candlestick charts with S/R zones, EMAs, volume, stop line).

## Data

Yahoo Finance via `yfinance` (batch download), cached per symbol as CSV in
`cache/` (12h max age). Universe: 74 curated HK large caps in `config.py`
(the old stock_screener 38 + extension). Filter: avg daily turnover ≥ HK$50M.

## Files

- `config.py` — universe + every threshold (tune edges here)
- `data.py` — fetch/cache layer
- `edges.py` — the 7 edge detectors + pivot/zone engine
- `screener.py` — scoring, setup classification, ranking
- `dashboard.py` — HTML report generator (plotly, dark theme)
- `main.py` — CLI

*Educational screening tool — not investment advice.*
