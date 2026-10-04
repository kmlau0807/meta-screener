"""Self-contained HTML dashboard: sortable results table + plotly charts
with S/R zones, EMAs, volume, and entry/stop annotations."""

import datetime
import json
import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as C
from edges import build_zones, rsi, macd

BG = "#14161c"
PANEL = "#1c1f27"
GRID = "#2a2e3a"
TXT = "#e6e8ee"
SUB = "#9aa0b0"
GREEN = "#e35454"   # HK convention: red = up
RED = "#2eaa6e"     # green = down
ACCENT = "#f0b90b"

CDN_FALLBACK = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'


def _plotly_inline() -> str:
    """Embed plotly.min.js directly so charts render fully offline
    (CDN may be blocked / unavailable when opening the file)."""
    try:
        import plotly
        p = os.path.join(os.path.dirname(plotly.__file__),
                         "package_data", "plotly.min.js")
        with open(p, "r", encoding="utf-8") as f:
            return f"<script>{f.read()}</script>"
    except Exception:
        return CDN_FALLBACK


def _build_fig(res, df):
    d = df.tail(C.CHART_BARS)
    zones = build_zones(df)
    close = res["close"]

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        row_heights=[0.52, 0.16, 0.16, 0.16], vertical_spacing=0.03,
    )
    bull = d["Close"] >= d["Open"]
    # candlesticks (split so legend colors are right)
    fig.add_trace(go.Candlestick(
        x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
        name="Price",
        increasing_line_color=GREEN, increasing_fillcolor=GREEN,
        decreasing_line_color=RED, decreasing_fillcolor=RED,
        opacity=0.95,
    ), row=1, col=1)
    for n, col in ((10, "#5b8def"), (20, "#f0b90b"), (50, "#b06ab3")):
        fig.add_trace(go.Scatter(
            x=d.index, y=d[f"EMA{n}"], name=f"EMA{n}",
            line=dict(width=1.2, color=col), opacity=0.9,
        ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=d.index, y=d["Volume"], name="Volume",
        marker_color=[GREEN if b else RED for b in bull],
        marker_line_width=0, opacity=0.55, showlegend=False,
    ), row=2, col=1)
    # --- RSI (row 3) ---
    r = rsi(d["Close"], 14)
    fig.add_trace(go.Scatter(
        x=d.index, y=r, name="RSI(14)", line=dict(width=1.1, color="#f0b90b"),
        showlegend=False,
    ), row=3, col=1)
    fig.add_hline(y=70, row=3, col=1, line_dash="dot", line_color=RED, line_width=0.8)
    fig.add_hline(y=30, row=3, col=1, line_dash="dot", line_color=GREEN, line_width=0.8)
    # --- MACD (row 4) ---
    m, s, h = macd(d["Close"])
    fig.add_trace(go.Bar(
        x=d.index, y=h, name="MACD hist",
        marker_color=[GREEN if v >= 0 else RED for v in h],
        marker_line_width=0, showlegend=False, opacity=0.6,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=d.index, y=m, name="MACD", line=dict(width=1.1, color="#5b8def"),
        showlegend=False,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=d.index, y=s, name="Signal", line=dict(width=1.1, color="#b06ab3"),
        showlegend=False,
    ), row=4, col=1)

    # --- divergence markers (RSI row 3 / MACD row 4) ---
    dv = res.get("divergence") or {}
    def _mark(date, ser, yrow, bullish):
        if not date or date not in d.index:
            return
        sym = "triangle-up" if bullish else "triangle-down"
        col = GREEN if bullish else RED   # GREEN = up (HK conv), RED = down
        fig.add_trace(go.Scatter(
            x=[date], y=[float(ser.loc[date])], mode="markers",
            marker=dict(symbol=sym, size=12, color=col, line=dict(width=1, color="white")),
            showlegend=False,
        ), row=yrow, col=1)
    _mark(dv.get("bull_rsi_date"), r, 3, True)
    _mark(dv.get("bear_rsi_date"), r, 3, False)
    _mark(dv.get("bull_macd_date"), m, 4, True)
    _mark(dv.get("bear_macd_date"), m, 4, False)

    # --- S/R zones (shaded band) + S/R lines (dashed at zone mid)
    # J Law: S/R is a *zone*, but the pivot mid acts as the key line to trade.
    # Classify each zone by its MID vs close so a zone inside price is not
    # drawn as BOTH support and resistance.
    below = [z for z in zones if z["mid"] <= close]
    above = [z for z in zones if z["mid"] > close]
    for z in sorted(below, key=lambda z: -z["high"])[:2]:
        fig.add_hrect(
            y0=z["low"], y1=z["high"], row=1, col=1,
            fillcolor=GREEN, opacity=0.10, line_width=0,
            annotation_text=f"支持區 {z['touches']}t",
            annotation_font_color=GREEN, annotation_position="inside left",
        )
        fig.add_hline(
            y=z["mid"], row=1, col=1, line_dash="dash", line_width=1.1,
            line_color=GREEN,
            annotation_text=f"支持線 {z['mid']:.2f}",
            annotation_font_color=GREEN, annotation_position="bottom right",
        )
    for z in sorted(above, key=lambda z: z["low"])[:2]:
        fig.add_hrect(
            y0=z["low"], y1=z["high"], row=1, col=1,
            fillcolor=RED, opacity=0.10, line_width=0,
            annotation_text=f"阻力區 {z['touches']}t",
            annotation_font_color=RED, annotation_position="inside left",
        )
        fig.add_hline(
            y=z["mid"], row=1, col=1, line_dash="dash", line_width=1.1,
            line_color=RED,
            annotation_text=f"阻力線 {z['mid']:.2f}",
            annotation_font_color=RED, annotation_position="top right",
        )

    # --- entry / stop annotation for META pullback setups
    if res["setup"] == "META PULLBACK" and res["support"].get("suggested_stop"):
        stop = res["support"]["suggested_stop"]
        fig.add_hline(y=stop, row=1, col=1, line_dash="dot",
                      line_color=RED, line_width=1.2,
                      annotation_text=f"stop {stop}", annotation_font_color=RED,
                      annotation_position="bottom right")

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font=dict(color=TXT, size=11),
        height=560, margin=dict(l=50, r=16, t=34, b=10),
        showlegend=True, legend=dict(orientation="h", y=1.06, x=0),
        xaxis_rangeslider_visible=False,
        xaxis=dict(gridcolor=GRID, rangebreaks=[dict(bounds=["sat", "mon"])]),
        yaxis=dict(gridcolor=GRID),
        yaxis2=dict(gridcolor=GRID),
        yaxis3=dict(gridcolor=GRID, range=[0, 100], fixedrange=False),
        yaxis4=dict(gridcolor=GRID),
    )
    return fig


def _fig_for(res, df):
    return _build_fig(res, df).to_html(
        full_html=False, include_plotlyjs=False,
        config={"displayModeBar": False, "responsive": True})


def build_chart_png(res, df, outpath):
    """Render one chart to PNG (for Telegram sendPhoto)."""
    try:
        fig = _build_fig(res, df)
        fig.write_image(outpath, format="png", engine="kaleido",
                        width=1000, height=620, scale=2)
        return outpath
    except Exception as e:
        print(f"[chart png] {res['symbol']} failed: {e}")
        return None


# J Law playbook per setup (short, in KM's Cantonese-leaning tone)
_SETUP_PLAY = {
    "META PULLBACK": "多重優勢收斂：趨勢 + 支持區 + 週線 + 拉回/回測。等價格回踩支持區出下影線＋縮量＝買點，止損放支持區下方。",
    "META RETEST": "突破後回測翻轉區（舊阻力變新支持）＝確認。成交縮小＋企穩即買，止損放區下。",
    "BREAKOUT": "放量突破阻力區。等回測區（翻轉）確認先出手，唔追突破當枝。",
    "TREND PULLBACK": "趨勢中健康低量拉回。等拉回到支持區/均線出下影線才考慮，順勢低吸。",
    "TRENDING": "趨勢向上但未到支持區，屬觀察；等低量拉回才出手。",
    "RS LEADER": "相對強度強（大市跌佢升＝照妖鏡）但未完全收斂，列入觀察名單；等回踩支持區才出手。",
}


def _explain(res, df):
    """Per-chart plain-language explanation (Cantonese-leaning, no emoji)."""
    close = res["close"]
    zones = build_zones(df)
    sup, t, v, pb, bo, rs = (res.get("support"), res.get("trend"),
                              res.get("volume"), res.get("pullback"),
                              res.get("breakout"), res.get("rs"))
    L = []

    # --- support zone + line ---
    below = [z for z in zones if z["mid"] <= close]
    if below:
        z = max(below, key=lambda x: x["high"])
        dist = (close - z["high"]) / close
        if sup.get("active"):
            L.append(f"支持區 {z['low']:.2f}–{z['high']:.2f}（{z['touches']} 次觸及），現價上方 "
                     f"{dist*100:.1f}%；支持線喺 {z['mid']:.2f}。止損 {sup.get('suggested_stop')} "
                     f"（風險 {sup.get('risk_pct')*100:.1f}%）")
        else:
            L.append(f"最近支持區 {z['low']:.2f}–{z['high']:.2f}（{z['touches']} 觸及），現價上方 "
                     f"+{dist*100:.1f}%；支持線 {z['mid']:.2f}")

    # --- resistance zone + line ---
    above = [z for z in zones if z["mid"] > close]
    if above:
        z = min(above, key=lambda x: x["low"])
        dist = (z["low"] - close) / close
        L.append(f"最近阻力區 {z['low']:.2f}–{z['high']:.2f}（{z['touches']} 觸及），現價上方 "
                 f"+{dist*100:.1f}%；阻力線 {z['mid']:.2f}")

    # --- trend ---
    if t.get("active"):
        L.append(f"趨勢：強勢 {t['score']}/5 項達標，20日回報 {t['ret20']*100:+.1f}%，"
                 f"陽燭比例 {t['green_ratio']*100:.0f}%（EMA10/20/50 多頭排列）")

    # --- volume fuel ---
    if v.get("active"):
        L.append(f"成交動力：上升日成交 / 下跌日 = {v['up_down_vol_ratio']}x（放量上升＝燃料足）")

    # --- pullback health ---
    if pb.get("active"):
        L.append(f"低量拉回：由 {pb['days_since_high']} 日前高位回調 {pb['depth']*100:.1f}%，"
                 f"量比 {pb['pull_vol_vs_avg']}x（收縮＝健康拉回）")

    # --- breakout ---
    if bo.get("active"):
        L.append(f"突破：{bo['date']} 成交 {bo['vol_mult']}x 突破區 {bo['zone_low']}–{bo['zone_high']}")

    # --- relative strength ---
    if rs.get("active"):
        if rs.get("down_market_up_stock"):
            L.append(f"RS 相對強度：大市跌佢升（照妖鏡）！20/60/120日超額 "
                     f"{rs['rs_20']*100:+.1f}% / {rs['rs_60']*100:+.1f}% / {rs['rs_120']*100:+.1f}%")
        else:
            L.append(f"RS 相對強度：超額 20/60/120日 "
                     f"{rs['rs_20']*100:+.1f}% / {rs['rs_60']*100:+.1f}% / {rs['rs_120']*100:+.1f}%")

    # --- RSI / MACD ---
    r = rsi(df["Close"], 14)
    rsi_now = float(r.iloc[-1])
    rsi_state = "超買(>70)" if rsi_now > 70 else "超賣(<30)" if rsi_now < 30 else "中性區"
    m, sig, hist = macd(df["Close"])
    macd_now, sig_now, hist_now = float(m.iloc[-1]), float(sig.iloc[-1]), float(hist.iloc[-1])
    cross = "金叉(EMA12>EMA26 且 MACD>Signal)" if (macd_now > sig_now and macd_now > 0) else \
            "死叉(MACD<Signal)" if macd_now < sig_now else "MACD 於 0 上(偏強)"
    L.append(f"RSI(14) = {rsi_now:.1f}（{rsi_state}）")
    L.append(f"MACD(12,26,9) = {macd_now:.3f}，Signal {sig_now:.3f}，柱 {hist_now:+.3f}（{cross}）")

    # --- divergence ---
    dv = res.get("divergence") or {}
    if dv.get("active") or dv.get("bear_rsi") or dv.get("bear_macd"):
        L.append(f"背離信號：{dv.get('detail')}")

    # --- playbook ---
    play = _SETUP_PLAY.get(res["setup"], "邊緣情況，未足夠 edge 收斂，唔係買賣信號。")
    L.append(f"操作邏輯（{res['setup']}）：{play}")
    return L


def _explain_html(res, df) -> str:
    return "<br>".join(_explain(res, df))


def build_markdown_summary(results, frames, market: str) -> str:
    """Markdown scan summary for email/Telegram (each stock = the chart
    explanation in bullet form)."""
    stamp = datetime.date.today().isoformat()
    bench = C.RS_BENCHMARK
    cur = C.CURRENCY
    meta = [r for r in results if r["meta"]]
    leaders = [r for r in results if r.get("rs_leader")]
    lines = [
        f"# META Screener — {market.upper()} ({cur})",
        f"生成日期：{stamp} ｜ Benchmark：{bench} ｜ 掃描 {len(results)} 隻",
        f"",
        f"## 信號統計",
        f"- META SETUP：{len(meta)} 隻",
        f"- RS LEADER（強相對強度 watchlist）：{len(leaders)} 隻",
        f"",
    ]
    def _block(r):
        sup = r["support"]
        stop = sup.get("suggested_stop") if sup.get("active") else None
        risk = sup.get("risk_pct") if sup.get("active") else None
        head = (f"## {r['symbol']} {r['name']} — {r['setup']} "
                f"(META {r['score']:.1f})")
        sub = (f"收盤 {r['close']:.2f} {cur} ｜ 日期 {r['date']} ｜ "
               f"活躍 edge：{' '.join(r['active_edges'])}"
               + (f" ｜ 止損 {stop}（風險 {risk*100:.1f}%）" if stop else ""))
        df = frames.get(r["symbol"])
        expl = "\n".join(f"- {x}" for x in _explain(r, df))
        return f"{head}\n{sub}\n{expl}"
    if meta:
        lines.append("## META SETUP")
        lines.append("")
        lines += [_block(r) for r in meta]
    if leaders:
        lines.append("")
        lines.append("## RS LEADER（觀察名單）")
        lines.append("")
        lines += [_block(r) for r in leaders]
    lines.append("")
    lines.append("---")
    lines.append("M.E.T.A. 多重優勢框架篩選信號，非投資建議。RSI/MACD/S/R 數值僅供參考，"
                 "出手前自行核對圖表與止損位。")
    return "\n".join(lines)


def _rows(results, chart_syms):
    rows = []
    for i, r in enumerate(results, 1):
        sup = r["support"]
        stop = sup.get("suggested_stop") if sup.get("active") else None
        risk = sup.get("risk_pct") if sup.get("active") else None
        dist = sup.get("dist_pct") if sup.get("active") else None
        link = (f'<a href="#chart-{r["symbol"]}">{r["symbol"]}</a>'
                if r["symbol"] in chart_syms else r["symbol"])
        edges = " ".join(
            f'<span class="edge{"" if e in ("AtSupport", "Weekly") else " e2"}">{e}</span>'
            for e in r["active_edges"]) or '<span class="dim">-</span>'
        pct = min(100.0, r["score"] / C.MAX_SCORE * 100)
        rows.append(f"""<tr>
<td class="dim">{i}</td>
<td class="sym">{link}</td>
<td>{r["name"]}</td>
<td class="num">{r["close"]:.2f}</td>
<td>{_setup_badge(r["setup"])}</td>
<td><div class="scorebar"><div style="width:{pct:.0f}%"></div></div><span class="num">{r["score"]:.1f}</span></td>
<td class="edges">{edges}</td>
<td class="num">{f"{dist * 100:.1f}%" if dist is not None else "-"}</td>
<td class="num">{f"{stop:.2f}" if stop else "-"}</td>
<td class="num">{f"{risk * 100:.1f}%" if risk is not None else "-"}</td>
<td class="num dim">{r["turnover_m"]:.0f}M</td>
</tr>""")
    return "\n".join(rows)


def _setup_badge(s):
    color = {"META PULLBACK": GREEN, "META RETEST": GREEN, "BREAKOUT": ACCENT,
             "TREND PULLBACK": "#5b8def", "TRENDING": "#7a8299",
             "RS LEADER": GREEN}.get(s, "#555")
    return f'<span class="badge" style="background:{color}22;color:{color};border:1px solid {color}55">{s}</span>' if s != "-" else '<span class="dim">-</span>'


def build_dashboard(results, frames, outpath, meta_shown=None):
    top = results[:C.DASHBOARD_TOP_N]
    chart_syms = {r["symbol"] for r in top}
    meta_count = sum(1 for r in results if r["meta"])

    charts = []
    from screener import prepare_chart_data
    for r in top:
        d = prepare_chart_data(frames[r["symbol"]])
        sub = " &middot; ".join(r["active_edges"]) or "no active edges"
        charts.append(f"""
<section class="card" id="chart-{r['symbol']}">
  <div class="chart-head">
    <div><span class="csym">{r["symbol"]}</span> <span class="cname">{r["name"]}</span>
      <span class="dim">{r["date"]}</span></div>
    <div>{_setup_badge(r["setup"])} <span class="cscore">META {r["score"]:.1f}</span></div>
  </div>
  <div class="edges-line">{sub}</div>
  {_fig_for(r, d)}
  <div class="explain">{_explain_html(r, d)}</div>
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>META Screener &middot; {datetime.date.today().isoformat()}</title>
{_plotly_inline()}
<style>
:root {{ --bg:{BG}; --panel:{PANEL}; --grid:{GRID}; --txt:{TXT}; --sub:{SUB}; --accent:{ACCENT}; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--txt);
  font:14px/1.5 -apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-size:22px; margin:0; }}
.sub {{ color:var(--sub); margin:6px 0 18px; }}
.kpis {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:22px; }}
.kpi {{ background:var(--panel); border:1px solid var(--grid); border-radius:10px;
  padding:12px 18px; min-width:130px; }}
.kpi b {{ display:block; font-size:22px; color:var(--accent); }}
.kpi span {{ color:var(--sub); font-size:12px; }}
.card {{ background:var(--panel); border:1px solid var(--grid); border-radius:12px;
  padding:16px; margin:18px 0; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; color:var(--sub); font-weight:600; padding:8px 10px;
  border-bottom:1px solid var(--grid); cursor:pointer; user-select:none; white-space:nowrap; }}
th:hover {{ color:var(--txt); }}
td {{ padding:7px 10px; border-bottom:1px solid #23262f; white-space:nowrap; }}
tr:hover td {{ background:#20242e; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.sym {{ font-weight:700; }}
.dim {{ color:var(--sub); }}
a {{ color:var(--accent); text-decoration:none; }}
.badge {{ padding:2px 9px; border-radius:20px; font-size:11.5px; font-weight:600; }}
.scorebar {{ display:inline-block; width:64px; height:7px; background:#262a35;
  border-radius:4px; vertical-align:middle; margin-right:7px; overflow:hidden; }}
.scorebar div {{ height:100%; background:var(--accent); }}
.edge {{ background:{GREEN}1c; color:{GREEN}; border:1px solid {GREEN}44;
  padding:1px 7px; border-radius:4px; font-size:11px; margin-right:3px; }}
.edge.e2 {{ background:#5b8def1c; color:#7fa7ef; border-color:#5b8def44; }}
.chart-head {{ display:flex; justify-content:space-between; align-items:center; }}
.csym {{ font-size:17px; font-weight:800; }}
.cname {{ color:var(--sub); }}
.cscore {{ font-weight:700; color:var(--accent); margin-left:8px; }}
.edges-line {{ color:var(--sub); font-size:12px; margin:2px 0 6px; }}
.explain {{ background:#161922; border:1px solid var(--grid); border-left:3px solid var(--accent);
  border-radius:8px; padding:11px 14px; margin-top:10px; font-size:12.5px; line-height:1.75; }}
.explain b {{ color:var(--txt); }}
footer {{ color:var(--sub); font-size:12px; margin-top:30px; line-height:1.7; }}
</style></head><body><div class="wrap">
<h1>Multiple Edge Trading Area (META) Screener</h1>
<div class="sub">Edges converge = high-probability zone &middot; generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<div class="kpis">
<div class="kpi"><b>{len(results)}</b><span>stocks screened</span></div>
<div class="kpi"><b>{meta_count}</b><span>META setups (&ge;{C.META_SETUP_MIN_SCORE:.0f} score)</span></div>
<div class="kpi"><b>{sum(1 for r in results if r['setup'] == 'BREAKOUT')}</b><span>breakouts</span></div>
<div class="kpi"><b>{sum(1 for r in results if r.get('rs_leader'))}</b><span>RS leaders</span></div>
<div class="kpi"><b>{sum(1 for r in results if r['trend']['active'])}</b><span>strong trends</span></div>
</div>

<div class="card">
<table id="tbl">
<thead><tr>
<th>#</th><th>Symbol</th><th>Name</th><th class="num">Close</th><th>Setup</th>
<th> META score</th><th>Active edges</th><th class="num">Dist to S</th>
<th class="num">Stop</th><th class="num">Risk</th><th class="num">Turnover</th>
</tr></thead>
<tbody>
{_rows(results, chart_syms)}
</tbody></table>
</div>

<h2 style="font-size:17px;margin-top:28px;">Charts &middot; top {len(top)} by META score</h2>
{''.join(charts)}

<footer>
Edge key: <b>Trend</b> strong uptrend (candle dominance, stacked EMAs, HH/HL) &middot;
<b>AtSupport</b> price at a clustered pivot support zone &middot;
<b>Weekly</b> higher-timeframe uptrend &middot;
<b>LowVolPB</b> shallow low-volume pullback &middot;
<b>VolFuel</b> up-volume &gt; down-volume &middot;
<b>Breakout</b> volume-confirmed zone break &middot;
<b>Retest</b> retest of flipped zone.<br>
Setups: <b>META PULLBACK</b> = trend + at support + weekly + pullback/retest convergence &middot;
<b>RS LEADER</b> = strong relative strength vs benchmark but not full META convergence (watchlist) &middot;
stop = below zone (half-ATR buffer). Scores are relative screening signals, not investment advice.<br>
S/R: shaded band = <b>zone</b> (price area where pivots cluster) &middot; dashed line = <b>line</b> (zone midpoint, the key level to trade). Green = support, red = resistance.
</footer>
</div>
<script>
// click-to-sort table
document.querySelectorAll('#tbl th').forEach((th, idx) => {{
  th.addEventListener('click', () => {{
    const tb = document.querySelector('#tbl tbody');
    const rows = [...tb.rows];
    const asc = th.dataset.asc !== 'true';
    th.dataset.asc = asc;
    rows.sort((a, b) => {{
      let x = a.cells[idx].innerText.trim(), y = b.cells[idx].innerText.trim();
      const nx = parseFloat(x.replace(/[^0-9.-]/g, '')), ny = parseFloat(y.replace(/[^0-9.-]/g, ''));
      if (!isNaN(nx) && !isNaN(ny) && /^[-0-9.%M]*$/.test(x)) return asc ? nx - ny : ny - nx;
      return asc ? x.localeCompare(y) : y.localeCompare(x);
    }});
    rows.forEach(r => tb.appendChild(r));
  }});
}});
</script>
</body></html>"""

    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    return outpath
