"""META screening pipeline: run all edge detectors, score convergence,
classify the setup, and rank the universe."""

import pandas as pd

import config as C
from data import avg_turnover_hkd
from edges import (
    build_zones,
    edge_strong_trend,
    edge_volume_pattern,
    edge_low_vol_pullback,
    edge_near_support,
    edge_htf_alignment,
    edge_breakout_retest,
    ema,
)

EDGE_LABELS = {
    "trend": "Trend",
    "support": "AtSupport",
    "htf": "Weekly",
    "pullback": "LowVolPB",
    "volume": "VolFuel",
    "breakout": "Breakout",
    "retest": "Retest",
}


def analyze_symbol(symbol: str, name: str, df: pd.DataFrame):
    """Run all edges on one symbol. Returns result dict or None if filtered."""
    if len(df) < C.MIN_BARS:
        return None, "insufficient history"

    turnover = avg_turnover_hkd(df)
    if turnover < C.MIN_AVG_TURNOVER:
        return None, f"turnover {turnover/1e6:.0f}M < {C.MIN_AVG_TURNOVER/1e6:.0f}M"

    zones = build_zones(df)
    trend = edge_strong_trend(df)
    volume = edge_volume_pattern(df)
    pullback = edge_low_vol_pullback(df)
    support = edge_near_support(df, zones)
    htf = edge_htf_alignment(df)
    br = edge_breakout_retest(df, zones)
    breakout, retest = br["breakout"], br["retest"]

    # ---- weighted META score ----
    score = 0.0
    score += C.EDGE_WEIGHTS["trend"] * trend["score"] / 5.0
    if support["active"]:
        score += C.EDGE_WEIGHTS["support"]
    if htf["active"]:
        score += C.EDGE_WEIGHTS["htf"]
    if pullback["active"]:
        score += C.EDGE_WEIGHTS["pullback"]
    if volume["active"]:
        score += C.EDGE_WEIGHTS["volume"]
    if breakout["active"]:
        score += C.EDGE_WEIGHTS["breakout"]
    if retest["active"]:
        score += C.EDGE_WEIGHTS["retest"]
    score = round(score, 2)

    # ---- setup classification (edges must CONVERGE) ----
    if support["active"] and trend["active"] and htf["active"] and (
        pullback["active"] or retest["active"] or support.get("wick_into_zone")
    ):
        setup = "META PULLBACK"
    elif retest["active"] and htf["active"]:
        setup = "META RETEST"
    elif breakout["active"] and htf["active"] and trend["active"]:
        setup = "BREAKOUT"
    elif trend["active"] and htf["active"] and pullback["active"]:
        setup = "TREND PULLBACK"
    elif trend["active"] and htf["active"]:
        setup = "TRENDING"
    else:
        setup = "-"

    active_edges = [
        EDGE_LABELS[k] for k, v in [
            ("trend", trend["active"]), ("support", support["active"]),
            ("htf", htf["active"]), ("pullback", pullback["active"]),
            ("volume", volume["active"]), ("breakout", breakout["active"]),
            ("retest", retest["active"]),
        ] if v
    ]

    res = {
        "symbol": symbol,
        "name": name,
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": round(float(df["Close"].iloc[-1]), 2),
        "turnover_m": round(turnover / 1e6, 1),
        "score": score,
        "setup": setup,
        "active_edges": active_edges,
        "n_edges": len(active_edges),
        "trend": trend,
        "volume": volume,
        "pullback": pullback,
        "support": support,
        "htf": htf,
        "breakout": breakout,
        "retest": retest,
        "meta": score >= C.META_SETUP_MIN_SCORE and setup != "-",
    }
    return res, "ok"


def screen(frames: dict, names: dict):
    """Screen all {symbol: df}. Returns ranked list of result dicts."""
    results, rejected = [], []
    for symbol, df in frames.items():
        res, status = analyze_symbol(symbol, names.get(symbol, symbol), df)
        if res is None:
            rejected.append((symbol, status))
        else:
            results.append(res)

    # rank: META setups first (by score), then everything else by score
    results.sort(key=lambda r: (not r["meta"], -r["score"], -r["n_edges"]))
    return results, rejected


def prepare_chart_data(df: pd.DataFrame, bars=C.CHART_BARS):
    """Trim to the last N bars and add EMA columns for charting."""
    d = df.tail(bars).copy()
    for n in (10, 20, 50):
        # recompute on full history so EMAs are warm at the window edge
        d[f"EMA{n}"] = ema(df["Close"], n).tail(bars)
    return d
