"""Edge detectors implementing the Multiple Edge Trading Area (META) framework.

Each detector returns a dict with at least {'active': bool, 'label': str}.
The screener combines independent edges: the more that converge at one
price area, the stronger the META setup.
"""

import numpy as np
import pandas as pd

import config as C


# ---------------------------------------------------------------- helpers

def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def find_pivots(df: pd.DataFrame, k: int = 3):
    """Return (pivot_highs, pivot_lows) as [(date, price), ...].

    A pivot high's High is the strict max of its +/-k window.
    """
    ph, pl = [], []
    highs, lows = df["High"], df["Low"]
    n = len(df)
    for i in range(k, n - k):
        wh = highs.iloc[i - k: i + k + 1]
        if highs.iloc[i] >= wh.max() and (wh == highs.iloc[i]).sum() == 1:
            ph.append((df.index[i], float(highs.iloc[i])))
        wl = lows.iloc[i - k: i + k + 1]
        if lows.iloc[i] <= wl.min() and (wl == lows.iloc[i]).sum() == 1:
            pl.append((df.index[i], float(lows.iloc[i])))
    return ph, pl


def build_zones(df: pd.DataFrame, lookback=C.ZONE_LOOKBACK,
                tol=C.ZONE_TOL, min_touches=C.ZONE_MIN_TOUCHES,
                max_width=0.045):
    """Cluster swing pivots into horizontal support/resistance zones.

    Returns list of {'low','high','mid','touches','last_touch'} sorted by low.
    A zone is a *price area*, not a line (S/R is a zone per J Law).
    Clusters grow only while price stays within `tol` of the cluster mean and
    the total zone width stays under `max_width` (prevents chained mega-zones).
    """
    d = df.tail(lookback)
    if len(d) < 30:
        return []
    ph, pl = find_pivots(d, k=3)
    pts = sorted(
        [(p, dt) for dt, p in ph] + [(p, dt) for dt, p in pl],
        key=lambda x: x[0],
    )
    zones = []
    cluster = []
    for price, dt in pts:
        if cluster:
            mean = float(np.mean([p for p, _ in cluster]))
            too_far = price - mean > tol * price
            too_wide = price - min(p for p, _ in cluster) > max_width * price
            if too_far or too_wide:
                zones.append(cluster)
                cluster = []
        cluster.append((price, dt))
    if cluster:
        zones.append(cluster)

    out = []
    for z in zones:
        prices = [p for p, _ in z]
        out.append({
            "low": float(min(prices)),
            "high": float(max(prices)),
            "mid": float(np.mean(prices)),
            "touches": len(z),
            "last_touch": max(dt for _, dt in z),
        })
    out = [z for z in out if z["touches"] >= min_touches]
    out.sort(key=lambda z: z["low"])
    return out


# ---------------------------------------------------------------- Edge 1

def edge_strong_trend(df: pd.DataFrame):
    """Strong uptrend: dominant green candles, stacked EMAs, HH/HL structure,
    price hugging the 10/20 EMA and NOT touching the 50 EMA."""
    close = df["Close"]
    e10, e20, e50 = ema(close, 10), ema(close, 20), ema(close, 50)
    last = float(close.iloc[-1])

    body = close - df["Open"]
    green_ratio = float((body.tail(C.TREND_LOOKBACK) > 0).mean())

    ma_stack = (last > e20.iloc[-1] > e50.iloc[-1]) and (e10.iloc[-1] > e20.iloc[-1])
    no_touch_50 = bool(df["Low"].tail(10).min() > e50.tail(10).min())

    ph, pl = find_pivots(df.tail(120), 3)
    hh = len(ph) >= 2 and ph[-1][1] > ph[-2][1]
    hl = len(pl) >= 2 and pl[-1][1] > pl[-2][1]

    ret20 = float(last / close.iloc[-(C.TREND_LOOKBACK + 1)] - 1) if len(df) > C.TREND_LOOKBACK + 1 else 0.0

    checks = {
        "green_candles": green_ratio >= C.GREEN_RATIO_MIN,
        "ma_stack": bool(ma_stack),
        "above_ema50_10d": no_touch_50,
        "hh_hl_structure": bool(hh and hl),
        "momentum_20d": ret20 >= C.RET20_MIN,
    }
    score = int(sum(checks.values()))
    return {
        "active": score >= C.TREND_MIN_CHECKS,
        "score": score,
        "checks": checks,
        "green_ratio": round(green_ratio, 2),
        "ret20": round(ret20, 3),
    }


# ---------------------------------------------------------------- Edge 2

def edge_volume_pattern(df: pd.DataFrame):
    """Volume is the fuel: up-days should carry more volume than down-days."""
    v, body = df["Volume"], df["Close"] - df["Open"]
    dnv = float(v[(body < 0)].tail(C.TREND_LOOKBACK).mean())
    upv = float(v[(body > 0)].tail(C.TREND_LOOKBACK).mean())
    ratio = upv / dnv if dnv > 0 else np.inf
    return {
        "active": ratio >= C.UPDOWN_VOL_RATIO,
        "up_down_vol_ratio": round(float(ratio), 2) if np.isfinite(ratio) else 99.0,
    }


# ---------------------------------------------------------------- Edge 3

def edge_low_vol_pullback(df: pd.DataFrame):
    """Healthy pullback: shallow decline from a recent swing high on
    contracting volume, retracing < ~62% of the prior up-leg."""
    close = df["Close"]
    win = df.tail(C.PULLBACK_WINDOW)
    hi_date = win["Close"].idxmax()
    hi = float(win["Close"].max())
    last = float(close.iloc[-1])

    pos = df.index.get_loc(df.index[-1]) - df.index.get_loc(hi_date)
    if pos < 1:
        return {"active": False, "reason": "at highs / no pullback"}

    depth = (hi - last) / hi
    in_pullback = 0 < depth <= C.PULLBACK_MAX_DEPTH

    vol50 = float(df["Volume"].rolling(50).mean().iloc[-1])
    seg = df.loc[hi_date:]
    pull_vol = float(seg["Volume"].mean())
    low_vol = vol50 > 0 and pull_vol < vol50

    # retracement of the prior up-leg
    _, pl = find_pivots(df.tail(120), 3)
    prior_lows = [p for dt, p in pl if dt < hi_date]
    retrace, retrace_ok = None, True
    if prior_lows and hi > prior_lows[-1]:
        leg = hi - prior_lows[-1]
        if leg > 0:
            retrace = (hi - last) / leg
            retrace_ok = retrace <= C.PULLBACK_MAX_RETRACE

    active = bool(in_pullback and low_vol and retrace_ok)
    return {
        "active": active,
        "depth": round(depth, 3),
        "days_since_high": int(pos),
        "pull_vol_vs_avg": round(pull_vol / vol50, 2) if vol50 > 0 else None,
        "retrace": round(retrace, 2) if retrace is not None else None,
    }


# ---------------------------------------------------------------- Edge 4

def edge_near_support(df: pd.DataFrame, zones):
    """Price sitting on / just above a support zone -> tight-stop entry."""
    if not zones:
        return {"active": False}
    close = float(df["Close"].iloc[-1])
    low = float(df["Low"].iloc[-1])
    a = float(atr(df).iloc[-1])

    below = [z for z in zones if z["high"] <= close * 1.005]
    if not below:
        return {"active": False}
    z = max(below, key=lambda x: x["high"])  # nearest support below price
    dist = (close - z["high"]) / close
    dipped = low <= z["high"] and close >= z["low"]  # wick into zone, held
    active = bool(dist <= C.NEAR_SUPPORT_PCT or dipped)
    stop = z["low"] - 0.5 * a
    risk = (close - stop) / close if stop < close else None
    return {
        "active": active,
        "zone_low": round(z["low"], 2),
        "zone_high": round(z["high"], 2),
        "touches": z["touches"],
        "dist_pct": round(dist, 3),
        "wick_into_zone": bool(dipped),
        "suggested_stop": round(stop, 2),
        "risk_pct": round(risk, 3) if risk is not None else None,
    }


# ---------------------------------------------------------------- Edge 5

def edge_htf_alignment(df: pd.DataFrame):
    """Weekly chart must be in an uptrend (higher timeframe dominance)."""
    try:
        w = df.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min",
             "Close": "last", "Volume": "sum"}
        ).dropna(subset=["Close"])
    except Exception:
        return {"active": False}
    if len(w) < C.HTF_EMA_SLOW + 5:
        return {"active": False}
    c = w["Close"]
    ef = ema(c, C.HTF_EMA_FAST)
    es = ema(c, C.HTF_EMA_SLOW)
    up = (
        c.iloc[-1] > ef.iloc[-1]
        and ef.iloc[-1] > es.iloc[-1]
        and ef.iloc[-1] >= ef.iloc[-C.HTF_EMA_FAST]
    )
    return {"active": bool(up)}


# ---------------------------------------------------------------- Edge 6/7

def edge_breakout_retest(df: pd.DataFrame, zones):
    """Volume-confirmed breakout above a zone; plus retest of the flipped
    zone (old resistance becomes new support)."""
    if not zones:
        return {"breakout": {"active": False}, "retest": {"active": False}}

    close, vol = df["Close"], df["Volume"]
    vol50 = df["Volume"].rolling(50).mean()
    last_pos = len(df) - 1

    for i in range(max(1, len(df) - C.BREAKOUT_LOOKBACK), len(df)):
        c, prev = float(close.iloc[i]), float(close.iloc[i - 1])
        for z in zones:
            crossed = prev <= z["high"] and c > z["high"] and prev >= z["low"] * 0.9
            if not crossed:
                continue
            vm = float(vol.iloc[i] / vol50.iloc[i]) if vol50.iloc[i] > 0 else 0.0
            if vm >= C.BREAKOUT_VOL_MULT:
                bk = {
                    "active": True,
                    "date": str(df.index[i].date()),
                    "bars_ago": last_pos - i,
                    "zone_low": round(z["low"], 2),
                    "zone_high": round(z["high"], 2),
                    "vol_mult": round(vm, 2),
                }
                # retest: price returned into the flipped zone
                lo, hi = z["low"], z["high"]
                in_zone = lo * (1 - C.RETEST_BAND) <= c_last(df) <= hi * (1 + C.RETEST_BAND)
                retest_active = bool(
                    last_pos - i >= 1 and in_zone and c_last(df) >= lo * 0.97
                )
                return {
                    "breakout": bk,
                    "retest": {"active": retest_active, **{k: bk[k] for k in ("zone_low", "zone_high", "date")}},
                }
    return {"breakout": {"active": False}, "retest": {"active": False}}


def c_last(df):
    return float(df["Close"].iloc[-1])
