"""META Screener — daily / scheduled runner.

Scans one or more markets, saves a dashboard per market, prints a concise
summary (META setups + RS leaders), and optionally emails the dashboards.

Usage:
    python daily_scan.py --market hk,us
    python daily_scan.py --market us --refresh
    python daily_scan.py --market hk,us --no-email      # local only
"""
import argparse
import datetime
import json
import os
import smtplib
import ssl
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import config as C
from data import fetch_symbols
from screener import screen
from dashboard import build_dashboard, build_markdown_summary


def run_market(market, refresh, top):
    """Screen one market; save dashboard; return (results, outpath)."""
    if market not in C.MARKETS:
        raise SystemExit(f"unknown market '{market}' (use {list(C.MARKETS)})")
    mkt = C.MARKETS[market]
    # resolve market-specific globals (shared module state)
    C.RS_BENCHMARK = mkt["benchmark"]
    C.MIN_AVG_TURNOVER = mkt["min_turnover"]
    C.CURRENCY = mkt["currency"]
    C.DASHBOARD_TOP_N = top

    if mkt.get("universe_source") == "nasdaq":
        from data import fetch_nasdaq_universe
        univ = fetch_nasdaq_universe()
        symbols = list(univ.keys())
        names = univ
        print(f"  nasdaq universe: {len(symbols)} symbols")
    else:
        symbols = list(mkt["universe"].keys())
        names = dict(mkt["universe"])
    fetch_list = list(symbols)
    if C.RS_BENCHMARK:
        fetch_list.append(C.RS_BENCHMARK)

    print(f"\n=== [{market.upper()}] fetching {len(symbols)} symbols "
          f"(bench {C.RS_BENCHMARK}) ===")
    frames = fetch_symbols(fetch_list, refresh=refresh)
    bench_df = frames.pop(C.RS_BENCHMARK, None) if C.RS_BENCHMARK else None
    if C.RS_BENCHMARK and bench_df is None:
        print(f"[WARN] benchmark {C.RS_BENCHMARK} unavailable -> RS edge disabled")
    print(f"Loaded {len(frames)}/{len(symbols)} symbols")

    results, rejected = screen(frames, names, bench_df=bench_df)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out = os.path.join(C.REPORT_DIR, f"meta_dashboard_{market}_{stamp}.html")
    build_dashboard(results, frames, out)
    print(f"Dashboard: {out}")

    # ---- markdown summary (for email/Telegram) ----
    md_out = os.path.join(C.REPORT_DIR, f"meta_summary_{market}_{stamp}.md")
    with open(md_out, "w", encoding="utf-8") as f:
        f.write(build_markdown_summary(results, frames, market))
    print(f"Summary MD: {md_out}")

    # ---- concise summary ----
    meta = [r for r in results if r["meta"]]
    leaders = [r for r in results if r.get("rs_leader")]
    print(f"  {len(results)} scanned | {len(rejected)} filtered | "
          f"{len(meta)} META setup(s) | {len(leaders)} RS leader(s)")
    for r in meta:
        sup = r["support"]
        stop = sup.get("suggested_stop")
        extra = (f" stop {stop} (risk {sup['risk_pct']*100:.1f}%)"
                 if stop else "")
        print(f"   META  {r['symbol']:<10} {r['setup']:<14} {r['score']:.1f}{extra}")
    for r in leaders:
        print(f"   RS    {r['symbol']:<10} {r['score']:.1f}  "
              f"{', '.join(r['active_edges'])}")

    # ---- chart PNGs for Telegram (META + RS leaders only) ----
    from screener import prepare_chart_data
    from dashboard import build_chart_png
    charts_dir = os.path.join(C.REPORT_DIR, f"charts_{market}_{stamp}")
    os.makedirs(charts_dir, exist_ok=True)
    chart_paths = []
    for r in (meta + leaders):
        d = prepare_chart_data(frames[r["symbol"]])
        p = build_chart_png(r, d, os.path.join(charts_dir, f"{r['symbol']}.png"))
        if p:
            chart_paths.append((r["symbol"], p))
    if chart_paths:
        print(f"Charts PNG: {len(chart_paths)} -> {charts_dir}")
    return results, out, md_out, chart_paths


def _summary_html(market, results):
    rows = []
    for r in results:
        if r["meta"] or r.get("rs_leader"):
            tag = "META" if r["meta"] else "RS"
            rows.append(
                f"<tr><td>{market.upper()}</td><td><b>{r['symbol']}</b></td>"
                f"<td>{r['name']}</td><td>{tag}</td><td>{r['setup']}</td>"
                f"<td>{r['score']:.1f}</td></tr>")
    return "\n".join(rows)


def send_email(paths, markets_results):
    host, user, pw = C.SMTP_HOST, C.SMTP_USER, C.SMTP_PASS
    to = C.EMAIL_TO
    if not (host and user and pw and to):
        print("[email] SMTP not configured (SMTP_HOST/USER/PASS/TO) -> skipped")
        return
    msg = MIMEMultipart()
    msg["Subject"] = f"META Screener daily — {datetime.date.today().isoformat()}"
    msg["From"] = f"{C.EMAIL_FROM_NAME} <{user}>"
    msg["To"] = ", ".join(to)

    body_rows = "\n".join(_summary_html(m, res) for m, res in markets_results)
    body = (f"<h2>META Screener — {datetime.date.today().isoformat()}</h2>"
            f"<table border='1' cellpadding='4' style='border-collapse:collapse'>"
            f"<tr><th>Mkt</th><th>Symbol</th><th>Name</th><th>Type</th>"
            f"<th>Setup</th><th>Score</th></tr>{body_rows}</table>"
            f"<p>Full dashboards attached. Not investment advice.</p>")
    msg.attach(MIMEText(body, "html"))

    for p in paths:
        with open(p, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f"attachment; filename={os.path.basename(p)}")
        msg.attach(part)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, C.SMTP_PORT, context=ctx) as s:
        s.login(user, pw)
        s.sendmail(user, to, msg.as_string())
    print(f"[email] sent to {', '.join(to)}")


def _tg_post(token, method, data=None, files=None):
    """POST to the Telegram Bot API using only stdlib (no requests dependency).

    `files` is a dict {field: local_path} for multipart upload (sendPhoto).
    Returns (http_status, raw_bytes). On network error returns (None, msg_bytes).
    """
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        boundary = "----METAscr" + uuid.uuid4().hex
        body = bytearray()
        for k, v in (data or {}).items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
            body += str(v).encode() + b"\r\n"
        for k, path in files.items():
            with open(path, "rb") as fh:
                content = fh.read()
            body += f"--{boundary}\r\n".encode()
            body += (f'Content-Disposition: form-data; name="{k}"; '
                     f'filename="{os.path.basename(path)}"\r\n').encode()
            body += b"Content-Type: image/png\r\n\r\n"
            body += content + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=bytes(body), method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        req = urllib.request.Request(url, method="POST")
        if data:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001 - report any network failure
        return None, str(e).encode()


def _discover_chat_id(token):
    """Find the chat_id from the most recent message sent to the bot."""
    status, raw = _tg_post(token, "getUpdates", data={"timeout": 1, "limit": 5})
    if status != 200:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not data.get("ok"):
        return None
    for upd in reversed(data.get("result", [])):
        for key in ("message", "channel_post", "edited_message"):
            if key in upd and "chat" in upd[key]:
                return upd[key]["chat"]["id"]
    return None


TELEGRAM_CAPTION_LIMIT = 1000  # Telegram sendPhoto caption hard cap is 1024 chars


def _parse_symbol_blocks(md_path, symbols=None):
    """Split the markdown summary into one explanation block per symbol.

    Returns {symbol: block_text}, where block_text is the heading line followed
    by every bullet until the next '##' heading. A heading is only treated as a
    symbol block when its first token is one of `symbols` — section headings
    like '## META SETUP' or '## RS LEADER（觀察名單）' are skipped.
    """
    try:
        text = open(md_path, encoding="utf-8").read()
    except OSError:
        return {}
    known = set(symbols) if symbols else None
    blocks, cur, buf = {}, None, []
    for ln in text.split("\n"):
        if ln.startswith("## "):
            if cur and buf:
                blocks[cur] = "\n".join(buf).strip()
            head = ln[3:].strip()
            first = head.split()[0] if head.split() else ""
            cur = first if (known is None or first in known) else None
            buf = [head] if cur else []
        elif cur is not None:
            buf.append(ln)
    if cur and buf:
        blocks[cur] = "\n".join(buf).strip()
    return blocks


def _summary_header(md_path, symbols=None):
    """Title + signal-count lines from the summary, WITHOUT per-stock detail.

    Keeps everything before the first symbol block, so you still get market,
    date, benchmark and META/RS counts as context for the charts that follow —
    but not the full per-stock explanation, which now lives in each caption.
    """
    try:
        text = open(md_path, encoding="utf-8").read()
    except OSError:
        return ""
    known = set(symbols) if symbols else None
    out = []
    for ln in text.split("\n"):
        if ln.startswith("## "):
            head = ln[3:].strip()
            first = head.split()[0] if head.split() else ""
            if known is None or first in known:
                break
        out.append(ln)
    return "\n".join(out).strip()


def send_telegram(md_path, chart_paths, send_summary=False):
    """Push one chart photo per signal stock to Telegram, each self-explaining.

    Uses only stdlib urllib (no requests). Each chart PNG is sent via sendPhoto
    with that stock's own explanation as its caption, so the default push is
    charts-only. Pass send_summary=True to ALSO send the full markdown summary
    first, split into <=3900-char chunks (Telegram hard limit 4096). Plain text
    (no parse_mode) so # headings / - bullets render literally. If TG_CHAT_ID is
    empty it is auto-discovered from the latest message to the bot.
    """
    token, chat = C.TG_BOT_TOKEN, C.TG_CHAT_ID
    if not token:
        print("[telegram] TG_BOT_TOKEN not set -> skipped")
        return
    if not chat:
        chat = _discover_chat_id(token)
        if chat:
            print(f"[telegram] auto-discovered chat_id={chat} "
                  f"(save it to .env TG_CHAT_ID to skip discovery)")
        else:
            print("[telegram] TG_CHAT_ID not set and no message found -> skipped. "
                  "Send a message to the bot first, then re-run.")
            return
    # ---- text: full summary only on request ----
    # Default is charts-only. Every chart already carries its own explanation as
    # its caption, so re-sending the whole summary first is pure duplication.
    if send_summary:
        text = open(md_path, encoding="utf-8").read()
        chunks, cur = [], ""
        for line in text.split("\n"):
            if len(cur) + len(line) + 1 > 3900:
                chunks.append(cur)
                cur = line
            else:
                cur = (cur + "\n" + line) if cur else line
        if cur:
            chunks.append(cur)
        ok = 0
        for i, ch in enumerate(chunks, 1):
            status, _ = _tg_post(token, "sendMessage",
                                 data={"chat_id": chat, "text": ch})
            if status == 200:
                ok += 1
            else:
                print(f"[telegram] chunk {i} HTTP {status}")
        print(f"[telegram] sent {ok}/{len(chunks)} text chunks from "
              f"{os.path.basename(md_path)}")
    else:
        head = _summary_header(md_path, [s for s, _ in chart_paths])
        if head:
            status, _ = _tg_post(token, "sendMessage",
                                 data={"chat_id": chat, "text": head})
            print(f"[telegram] header "
                  f"{'sent' if status == 200 else 'FAILED HTTP ' + str(status)}")
    # ---- chart photos, each captioned with its OWN explanation ----
    blocks = _parse_symbol_blocks(md_path, [s for s, _ in chart_paths])
    for sym, p in chart_paths:
        caption = blocks.get(sym, "").strip() or sym
        if len(caption) > TELEGRAM_CAPTION_LIMIT:
            caption = caption[:TELEGRAM_CAPTION_LIMIT - 1].rstrip() + "…"
        status, _ = _tg_post(token, "sendPhoto",
                             data={"chat_id": chat, "caption": caption},
                             files={"photo": p})
        if status == 200:
            print(f"[telegram] sent chart {sym}")
        else:
            print(f"[telegram] chart {sym} failed HTTP {status}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="META Screener daily runner")
    p.add_argument("--market", default="hk,us",
                   help="Comma-separated markets to scan (default: hk,us)")
    p.add_argument("--refresh", action="store_true", help="Bypass price cache")
    p.add_argument("--top", type=int, default=C.DASHBOARD_TOP_N,
                   help="Charts per dashboard")
    p.add_argument("--no-email", action="store_true", help="Skip email send")
    p.add_argument("--no-telegram", action="store_true", help="Skip Telegram push")
    p.add_argument("--telegram-summary", action="store_true",
                   help="Also send the full markdown summary text before the charts "
                        "(default is charts-only: each caption already carries its "
                        "own explanation)")
    args = p.parse_args()

    markets = [m.strip() for m in args.market.split(",") if m.strip()]
    paths, markets_results = [], []
    for m in markets:
        res, out, md_out, chart_paths = run_market(m, args.refresh, args.top)
        paths.append(out)
        paths.append(md_out)
        markets_results.append((m, res, md_out, chart_paths))

    if not args.no_email:
        send_email(paths, markets_results)
    if not args.no_telegram:
        for m, res, md_out, chart_paths in markets_results:
            send_telegram(md_out, chart_paths,
                          send_summary=args.telegram_summary)


if __name__ == "__main__":
    main()
