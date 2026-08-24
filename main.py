"""META Screener CLI.

Usage:
    python main.py                       # screen HK universe -> dashboard
    python main.py --symbols 0700.HK,AAPL,MSFT
    python main.py --refresh             # force refetch of price data
    python main.py --min-score 4 --top 20
    python main.py --no-dashboard        # console report only
"""

import argparse
import sys
from datetime import datetime

import config as C
from data import fetch_symbols
from dashboard import build_dashboard
from screener import screen


def parse_args():
    p = argparse.ArgumentParser(description="Multiple Edge Trading Area screener")
    p.add_argument("--symbols", type=str, default=None,
                   help="Comma-separated tickers (default: HK universe)")
    p.add_argument("--refresh", action="store_true", help="Bypass price cache")
    p.add_argument("--min-score", type=float, default=0.0,
                   help="Hide rows below this META score in the report")
    p.add_argument("--top", type=int, default=C.DASHBOARD_TOP_N,
                   help="Charts to embed in the dashboard")
    p.add_argument("--min-turnover", type=float, default=C.MIN_AVG_TURNOVER,
                   help="Min avg daily turnover (HKD/USD)")
    p.add_argument("--no-dashboard", action="store_true",
                   help="Skip HTML dashboard generation")
    return p.parse_args()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        names = {s: s for s in symbols}
    else:
        symbols = list(C.HK_UNIVERSE.keys())
        names = dict(C.HK_UNIVERSE)

    C.MIN_AVG_TURNOVER = args.min_turnover
    C.DASHBOARD_TOP_N = args.top

    print(f"META Screener - {len(symbols)} symbols")
    frames = fetch_symbols(symbols, refresh=args.refresh)
    print(f"Loaded price data for {len(frames)}/{len(symbols)} symbols\n")

    results, rejected = screen(frames, names)

    print(f"{'=' * 100}")
    print(f"{'SYM':<9} {'NAME':<16} {'CLOSE':>8} {'SETUP':<14} {'SCORE':>5} "
          f"{'EDGES':>5}  ACTIVE EDGES")
    print("-" * 100)
    shown = 0
    for r in results:
        if r["score"] < args.min_score:
            continue
        shown += 1
        print(f"{r['symbol']:<9} {r['name'][:16]:<16} {r['close']:>8.2f} "
              f"{r['setup']:<14} {r['score']:>5.1f} {r['n_edges']:>5}  "
              f"{', '.join(r['active_edges'])}")
    print("-" * 100)
    print(f"{shown} results | {len(rejected)} filtered (turnover/history)")
    meta = [r for r in results if r["meta"]]
    if meta:
        print(f"\n*** {len(meta)} META SETUP(S) ***")
        for r in meta:
            sup = r["support"]
            stop = sup.get("suggested_stop")
            risk = sup.get("risk_pct")
            extra = (f" | zone {sup['zone_low']}-{sup['zone_high']} "
                     f"stop {stop} (risk {risk*100:.1f}%)"
                     if sup.get("active") and stop else "")
            print(f"  {r['symbol']} {r['name']}: {r['setup']} "
                  f"score {r['score']}{extra}")

    if args.no_dashboard or not results:
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = f"{C.REPORT_DIR}/meta_dashboard_{stamp}.html"
    build_dashboard(results, frames, out)
    print(f"\nDashboard saved: {out}")


if __name__ == "__main__":
    main()
