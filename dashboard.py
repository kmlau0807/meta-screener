"""Self-contained HTML dashboard: sortable results table + plotly charts
with S/R zones, EMAs, volume, and entry/stop annotations."""

import datetime
import json
import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as C
from edges import build_zones

BG = "#14161c"
PANEL = "#1c1f27"
GRID = "#2a2e3a"
TXT = "#e6e8ee"
SUB = "#9aa0b0"
GREEN = "#e35454"   # HK convention: red = up
RED = "#2eaa6e"     # green = down
ACCENT = "#f0b90b"

CDN = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'


def _fig_for(res, df):
    d = df.tail(C.CHART_BARS)
    zones = build_zones(df)
    close = res["close"]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.02,
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
        marker_line_width=0, opacity=0.55,
    ), row=2, col=1)

    # --- S/R zones: nearest below (support, green) & above (resistance, red)
    below = [z for z in zones if z["high"] < close * 1.01]
    above = [z for z in zones if z["low"] > close * 0.99]
    for z in sorted(below, key=lambda z: -z["high"])[:2]:
        fig.add_hrect(
            y0=z["low"], y1=z["high"], row=1, col=1,
            fillcolor=GREEN, opacity=0.10, line_width=0,
            annotation_text=f"S ({z['touches']} touches)",
            annotation_font_color=GREEN, annotation_position="inside left",
        )
    for z in sorted(above, key=lambda z: z["low"])[:2]:
        fig.add_hrect(
            y0=z["low"], y1=z["high"], row=1, col=1,
            fillcolor=RED, opacity=0.10, line_width=0,
            annotation_text=f"R ({z['touches']} touches)",
            annotation_font_color=RED, annotation_position="inside left",
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
        height=430, margin=dict(l=50, r=16, t=34, b=10),
        showlegend=True, legend=dict(orientation="h", y=1.06, x=0),
        xaxis_rangeslider_visible=False,
        xaxis=dict(gridcolor=GRID, rangebreaks=[dict(bounds=["sat", "mon"])]),
        yaxis=dict(gridcolor=GRID),
        yaxis2=dict(gridcolor=GRID),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


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
             "TREND PULLBACK": "#5b8def", "TRENDING": "#7a8299"}.get(s, "#555")
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
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>META Screener &middot; {datetime.date.today().isoformat()}</title>
{CDN}
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
footer {{ color:var(--sub); font-size:12px; margin-top:30px; line-height:1.7; }}
</style></head><body><div class="wrap">
<h1>Multiple Edge Trading Area (META) Screener</h1>
<div class="sub">Edges converge = high-probability zone &middot; generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<div class="kpis">
<div class="kpi"><b>{len(results)}</b><span>stocks screened</span></div>
<div class="kpi"><b>{meta_count}</b><span>META setups (&ge;{C.META_SETUP_MIN_SCORE:.0f} score)</span></div>
<div class="kpi"><b>{sum(1 for r in results if r['setup'] == 'BREAKOUT')}</b><span>breakouts</span></div>
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
stop = below zone (half-ATR buffer). Scores are relative screening signals, not investment advice.
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
