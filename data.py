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


def avg_turnover_hkd(df: pd.DataFrame, months=6) -> float:
    """Average daily turnover (Close * Volume) over recent months."""
    cutoff = df.index.max() - pd.DateOffset(months=months)
    d = df[df.index >= cutoff]
    if d.empty:
        return 0.0
    return float((d["Close"] * d["Volume"]).mean())
