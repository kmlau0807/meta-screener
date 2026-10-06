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


_SLICK_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.slickcharts.com/",
}
_SLICK_SOURCES = (
    ("S&P 500", "https://www.slickcharts.com/sp500"),
    ("Nasdaq-100", "https://www.slickcharts.com/nasdaq100"),
)


def _parse_slickcharts(html: str) -> list[tuple[str, str]]:
    """[(symbol, company), ...] from a Slickcharts constituents table.

    Picks the first <table> whose header row contains a 'Symbol' column and
    reads that column (plus 'Company' when present). Ticker dots are normalised
    to dashes so e.g. BRK.B becomes Yahoo's BRK-B.
    """
    import re

    def _strip(s: str) -> str:
        s = re.sub(r"<[^>]+>", "", s)
        return (s.replace("&amp;", "&").replace("&nbsp;", " ")
                 .replace("&#39;", "'").strip())

    for tbl in re.findall(r"<table.*?</table>", html, flags=re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, flags=re.S)
        if len(rows) < 2:
            continue
        hdr = [_strip(c) for c in
               re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", rows[0], flags=re.S)]
        sym_idx = next((i for i, h in enumerate(hdr) if h.lower() == "symbol"), None)
        if sym_idx is None:
            continue
        name_idx = next((i for i, h in enumerate(hdr) if h.lower() == "company"), None)
        out = []
        for row in rows[1:]:
            cells = [_strip(c) for c in
                     re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)]
            if len(cells) <= sym_idx:
                continue
            sym = cells[sym_idx].strip().upper().replace(".", "-")
            if not sym:
                continue
            name = (cells[name_idx].strip()
                    if (name_idx is not None and len(cells) > name_idx) else "")
            out.append((sym, name))
        if out:
            return out
    raise RuntimeError("no Symbol table found")


def fetch_us_universe(cache_hours=24):
    """Dynamic US large-cap universe: S&P 500 union Nasdaq-100 (Slickcharts).

    Returns {symbol: name}, cached as JSON for `cache_hours`. Returns {} on
    failure so the caller can fall back to the static US_UNIVERSE in config.
    NOTE: uses requests, not bare urllib — Slickcharts 403s a minimal UA.
    """
    import json
    import requests

    p = os.path.join(CACHE_DIR, "us_universe.json")
    if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < cache_hours * 3600:
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    out = {}
    for label, url in _SLICK_SOURCES:
        try:
            r = requests.get(url, headers=_SLICK_HEADERS, timeout=25)
            r.raise_for_status()
            rows = _parse_slickcharts(r.text)
            for sym, name in rows:
                out.setdefault(sym, name)
            print(f"[us] fetched {label}: {len(rows)} constituents")
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {label} universe fetch failed: {e}")
    if out:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f)
        print(f"[us] fetched {len(out)} symbols")
    return out
