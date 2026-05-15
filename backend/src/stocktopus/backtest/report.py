"""HTML report generator for backtest results.

Produces a self-contained HTML file with:
- Summary metrics table
- Equity curve chart (via Chart.js CDN — no extra dependencies)
- Per-regime breakdown table
- Full trade log table
"""
# ruff: noqa: E501

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from stocktopus.backtest.records import BacktestMetrics, BacktestTrade

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stocktopus Backtest — {symbol}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 0; padding: 24px; background: #0f0f0f; color: #e0e0e0; }}
  h1, h2 {{ color: #00d4aa; margin-bottom: 8px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
           gap: 12px; margin-bottom: 32px; }}
  .card {{ background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 8px;
           padding: 16px; }}
  .card .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
                  color: #888; margin-bottom: 4px; }}
  .card .value {{ font-size: 24px; font-weight: 700; }}
  .pos {{ color: #00d4aa; }}
  .neg {{ color: #ff5c5c; }}
  .neu {{ color: #e0e0e0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px;
           margin-bottom: 32px; }}
  th {{ background: #1a1a2e; color: #888; text-align: left; padding: 8px 12px;
        font-weight: 500; text-transform: uppercase; font-size: 11px; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #1a1a1a; }}
  tr:hover td {{ background: #1a1a2e; }}
  .win {{ color: #00d4aa; }}
  .loss {{ color: #ff5c5c; }}
  canvas {{ max-width: 100%; margin-bottom: 32px; }}
  .section {{ margin-bottom: 40px; }}
</style>
</head>
<body>
<h1>Stocktopus Backtest Report — {symbol}</h1>
<div class="meta">Generated {generated_at} &nbsp;|&nbsp; {start_date} → {end_date} &nbsp;|&nbsp; Run ID: {run_id}</div>

<div class="grid">
  <div class="card"><div class="label">Net Return</div>
    <div class="value {return_class}">{total_return_pct:+.2f}%</div></div>
  <div class="card"><div class="label">Total Trades</div>
    <div class="value neu">{total_trades}</div></div>
  <div class="card"><div class="label">Win Rate</div>
    <div class="value {wr_class}">{win_rate_pct:.1f}%</div></div>
  <div class="card"><div class="label">Profit Factor</div>
    <div class="value {pf_class}">{profit_factor}</div></div>
  <div class="card"><div class="label">Expectancy / Trade</div>
    <div class="value {exp_class}">${expectancy:+.2f}</div></div>
  <div class="card"><div class="label">Max Drawdown</div>
    <div class="value neg">-{max_drawdown_pct:.2f}%</div></div>
  <div class="card"><div class="label">Sharpe Ratio</div>
    <div class="value {sharpe_class}">{sharpe_ratio}</div></div>
  <div class="card"><div class="label">Total Friction</div>
    <div class="value neu">${total_friction:.2f}</div></div>
</div>

<div class="section">
  <h2>Equity Curve</h2>
  <canvas id="equityChart"></canvas>
</div>

<div class="section">
  <h2>Per-Regime Breakdown</h2>
  {regime_table}
</div>

<div class="section">
  <h2>Trade Log ({total_trades} trades)</h2>
  {trade_table}
</div>

<script>
const labels = {equity_labels};
const data = {equity_data};
new Chart(document.getElementById('equityChart'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [{{
      label: 'Portfolio Value ($)',
      data,
      borderColor: '#00d4aa',
      backgroundColor: 'rgba(0,212,170,0.08)',
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.1,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color: '#888' }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#888', maxTicksLimit: 12 }}, grid: {{ color: '#1a1a1a' }} }},
      y: {{ ticks: {{ color: '#888' }}, grid: {{ color: '#1a1a1a' }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""


def _signed_class(value: float) -> str:
    return "pos" if value > 0 else ("neg" if value < 0 else "neu")


def render_report(
    metrics: BacktestMetrics,
    trades: list[BacktestTrade],
    equity_curve: list[float],
    run_id: str,
    output_path: Path,
) -> None:
    """Render the HTML report and write it to `output_path`."""

    # ── Equity chart data ─────────────────────────────────────────────────────
    step = max(1, len(equity_curve) // 500)  # downsample to ≤500 points for chart
    sampled = equity_curve[::step]
    labels = [str(i) for i in range(len(sampled))]

    # ── Per-regime table ──────────────────────────────────────────────────────
    regime_rows = "".join(
        f"<tr><td>{r}</td><td>{d['trades']}</td>"
        f'<td class="{"win" if d["win_rate"] >= 0.5 else "loss"}">{d["win_rate"] * 100:.1f}%</td>'
        f'<td class="{"win" if d["net_pnl"] >= 0 else "loss"}">${d["net_pnl"]:+.2f}</td></tr>'
        for r, d in sorted(metrics.regime_breakdown.items())
    )
    regime_table = (
        "<table><thead><tr><th>Regime</th><th>Trades</th><th>Win Rate</th>"
        "<th>Net P&amp;L</th></tr></thead><tbody>"
        + (regime_rows or "<tr><td colspan='4'>No trades</td></tr>")
        + "</tbody></table>"
    )

    # ── Trade log table ───────────────────────────────────────────────────────
    trade_rows = "".join(
        f"<tr>"
        f"<td>{t.entry_ts.strftime('%Y-%m-%d %H:%M')}</td>"
        f"<td>{t.exit_ts.strftime('%H:%M')}</td>"
        f"<td>${t.entry_price:.2f}</td>"
        f"<td>${t.exit_price:.2f}</td>"
        f"<td>{t.qty}</td>"
        f"<td>{t.exit_reason}</td>"
        f"<td>{t.regime}</td>"
        f'<td class="{"win" if t.net_pnl >= 0 else "loss"}">${t.net_pnl:+.2f}</td>'
        f"</tr>"
        for t in trades
    )
    trade_table = (
        "<table><thead><tr><th>Entry</th><th>Exit</th><th>Entry $</th><th>Exit $</th>"
        "<th>Qty</th><th>Reason</th><th>Regime</th><th>Net P&amp;L</th></tr></thead>"
        "<tbody>" + (trade_rows or "<tr><td colspan='8'>No trades in this period</td></tr>") + "</tbody></table>"
    )

    pf = metrics.profit_factor
    sharpe = metrics.sharpe_ratio

    html = _TEMPLATE.format(
        symbol=metrics.symbol,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        start_date=metrics.start_date.strftime("%Y-%m-%d"),
        end_date=metrics.end_date.strftime("%Y-%m-%d"),
        run_id=run_id,
        total_return_pct=metrics.total_return_pct,
        return_class=_signed_class(metrics.total_return_pct),
        total_trades=metrics.total_trades,
        win_rate_pct=metrics.win_rate * 100,
        wr_class="pos" if metrics.win_rate >= 0.5 else "neg",
        profit_factor=f"{pf:.2f}" if pf else "N/A",
        pf_class="pos" if (pf and pf > 1) else "neg",
        expectancy=metrics.expectancy,
        exp_class=_signed_class(metrics.expectancy),
        max_drawdown_pct=metrics.max_drawdown_pct,
        sharpe_ratio=f"{sharpe:.2f}" if sharpe else "N/A",
        sharpe_class="pos" if (sharpe and sharpe > 0.5) else "neg",
        total_friction=metrics.total_friction,
        equity_labels=json.dumps(labels),
        equity_data=json.dumps([round(v, 2) for v in sampled]),
        regime_table=regime_table,
        trade_table=trade_table,
    )

    output_path.write_text(html, encoding="utf-8")
