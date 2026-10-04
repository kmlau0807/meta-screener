"""Data layer: batch yfinance download with per-symbol CSV cache."""

import os
import time

import pandas as pd
import yfinance as yf

from config import CACHE_DIR, CACHE_MAX_AGE_HOURS, FETCH_PERIOD


def _cache_path(symbol: str) -> str:
    return os.path.join(CACHE_DIR, f"{symbol.replace('.', '_')}.csv")


def _cache_stale(symbol: str) -> bool:
    p = _cache_path(symbol)
    if not os.path.exists(p):
        return True
    return (time.time() - os.path.getmtime(p)) > CACHE_MAX_AGE_HOURS * 3600


def fetch_symbols(symbols, period=FETCH_PERIOD, refresh=False, verbose=True):
    """Batch-download daily OHLCV for symbols, caching each as CSV.

    Returns dict {symbol: DataFrame[Open, High, Low, Close, Volume]}.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    need = [s for s in symbols if refresh or _cache_stale(s)]

    if need and verbose:
        print(f"Downloading {len(need)} symbols from Yahoo Finance ...")

    if need:
        try:
            data = yf.download(
                need,
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        except Exception as e:  # network hiccup - fall back to cache only
            print(f"  [WARN] batch download failed: {e}")
            data = None

        for s in need:
            try:
                if data is None:
                    continue
                if isinstance(data.columns, pd.MultiIndex):
                    df = data[s].dropna(subset=["Close"])
                else:  # single-symbol frame
                    df = data.dropna(subset=["Close"])
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if not df.empty:
                    df.to_csv(_cache_path(s))
            except Exception:
                continue

    out = {}
    for s in symbols:
        p = _cache_path(s)
        if not os.path.exists(p):
            continue
        try:
            df = pd.read_csv(p, parse_dates=["Date"], index_col="Date")
        except Exception:
            continue
        if not df.empty:
            out[s] = df
    return out


def avg_turnover(df: pd.DataFrame, months=6) -> float:
    """Average daily turnover (Close * Volume) over recent months.

    Currency follows the symbol's quote (.HK -> HKD, US -> USD, ...); the
    screener labels it via config.CURRENCY.
    """
    cutoff = df.index.max() - pd.DateOffset(months=months)
    d = df[df.index >= cutoff]
    if d.empty:
        return 0.0
    return float((d["Close"] * d["Volume"]).mean())


def fetch_nasdaq_universe(cache_hours=24):
    """Full NASDAQ-listed universe from nasdaqtrader.com's daily symbol list.

    Returns {symbol: name}. ETFs / warrants / units (Symbol containing
    ^ . $ = ) and long odd tickers are skipped. Cached as JSON so the slow
    network fetch only happens once per `cache_hours`.
    """
    import json
    import io
    import csv
    import urllib.request

    p = os.path.join(CACHE_DIR, "nasdaq_universe.json")
    if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < cache_hours * 3600:
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(raw), delimiter="|")
        out = {}
        for row in reader:
            sym = (row.get("Symbol") or "").strip()
            name = (row.get("Security Name") or "").strip()
            if sym.startswith("File Creation"):   # trailer line
                break
            if not sym:
                continue
            if (row.get("Test Issue") or "").strip().upper() == "Y":
                continue
            if (row.get("ETF") or "").strip().upper() == "Y":
                continue
            lname = name.lower()
            if any(w in lname for w in ("warrant", " units", "unit rights",
                                        " rights", "preferred stock")):
                continue   # skip warrants / units / rights / preferreds
            if any(c in sym for c in "^.$="):   # skip warrants / units / prefs
                continue
            if len(sym) > 5:                       # skip odd long tickers
                continue
            out[sym] = name or sym
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f)
        print(f"[nasdaq] fetched {len(out)} symbols")
        return out
    except Exception as e:
        print(f"[WARN] nasdaq universe fetch failed: {e}")
        return {}
