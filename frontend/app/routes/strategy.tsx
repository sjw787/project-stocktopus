import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Activity, AlertTriangle, PlayCircle, RefreshCw } from "lucide-react";
import { api, type BacktestResult, type StrategyConfig } from "~/lib/api";

export const Route = createFileRoute("/strategy")({
  component: StrategyPage,
});

// ── Shared micro-components ───────────────────────────────────────────────────

function Card({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl p-4 ${className}`}
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
    >
      <h2
        className="text-xs font-semibold uppercase tracking-widest mb-3"
        style={{ color: "var(--text-muted)" }}
      >
        {title}
      </h2>
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex justify-center py-4">
      <RefreshCw size={18} className="animate-spin" style={{ color: "var(--text-muted)" }} />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 py-4 text-sm" style={{ color: "var(--text-muted)" }}>
      <AlertTriangle size={14} />
      {message}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex justify-between items-center py-1.5" style={{ borderBottom: "1px solid var(--border)" }}>
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="text-xs font-semibold">{value ?? "—"}</span>
    </div>
  );
}

// ── Strategy config card ──────────────────────────────────────────────────────

function StrategyConfigCard() {
  const { data, isLoading, isError } = useQuery<StrategyConfig>({
    queryKey: ["strategy-config"],
    queryFn: api.strategyConfig,
  });

  return (
    <Card title="Strategy Configuration">
      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <EmptyState message="Could not load strategy config" />
      ) : (
        <div>
          <Row label="Symbol" value={data.symbol} />
          <Row label="Timeframe" value={data.timeframe} />
          <Row label="Entry window" value={data.entry_time} />
          <Row label="Exit window" value={data.exit_time} />
          <Row label="Max daily trades" value={data.max_daily_trades} />
          <Row label="Position size" value={`${data.position_size_pct.toFixed(1)}%`} />
          <Row label="Stop loss" value={`${data.stop_loss_pct}%`} />
          <Row label="Take profit" value={`${data.take_profit_pct}%`} />
          <Row label="Required regime" value={data.require_regime ?? "any"} />
          <Row label="Min LLM confidence" value={data.min_llm_confidence ?? "none"} />
        </div>
      )}
    </Card>
  );
}

// ── Backtest form ─────────────────────────────────────────────────────────────

function defaultEnd() {
  return new Date().toISOString().slice(0, 10);
}
function defaultStart() {
  const d = new Date();
  d.setMonth(d.getMonth() - 3);
  return d.toISOString().slice(0, 10);
}

function BacktestRunner() {
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);

  const mutation = useMutation<BacktestResult, Error>({
    mutationFn: () => api.runBacktest({ symbol: "SPY", start, end, timeframe: "5m" }),
  });

  return (
    <Card title="Run Backtest">
      <div className="flex flex-wrap gap-3 mb-4 items-end">
        <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
          Start
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "4px 8px",
              color: "var(--text)",
              fontSize: 12,
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
          End
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "4px 8px",
              color: "var(--text)",
              fontSize: 12,
            }}
          />
        </label>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          {mutation.isPending ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : (
            <PlayCircle size={14} />
          )}
          Run
        </button>
      </div>

      {mutation.isError && (
        <div className="text-sm mb-3" style={{ color: "var(--red)" }}>
          Error: {mutation.error.message}
        </div>
      )}

      {mutation.data && <BacktestResults result={mutation.data} />}
    </Card>
  );
}

// ── Backtest results ──────────────────────────────────────────────────────────

function BacktestResults({ result }: { result: BacktestResult }) {
  const m = result.metrics;
  const pnlColor = m.net_profit >= 0 ? "var(--green)" : "var(--red)";

  return (
    <div className="space-y-4">
      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <MetricTile label="Net P&L" value={`$${m.net_profit.toFixed(2)}`} color={pnlColor} />
        <MetricTile label="Win Rate" value={`${(m.win_rate * 100).toFixed(1)}%`} />
        <MetricTile label="Profit Factor" value={m.profit_factor?.toFixed(2) ?? "—"} />
        <MetricTile label="Total Trades" value={String(m.total_trades)} />
        <MetricTile label="Max Drawdown" value={`${(m.max_drawdown * 100).toFixed(2)}%`} color="var(--red)" />
        <MetricTile label="Sharpe" value={m.sharpe_ratio?.toFixed(2) ?? "—"} />
        <MetricTile label="Avg Win" value={`$${m.avg_win.toFixed(2)}`} color="var(--green)" />
        <MetricTile label="Avg Loss" value={`$${m.avg_loss.toFixed(2)}`} color="var(--red)" />
      </div>

      {/* Trades table */}
      {result.trades.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
            Trades ({result.trades.length})
          </h3>
          <div style={{ overflowX: "auto" }}>
            <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                  <th className="text-left py-1 pr-3">Entry</th>
                  <th className="text-left py-1 pr-3">Dir</th>
                  <th className="text-right py-1 pr-3">Entry $</th>
                  <th className="text-right py-1 pr-3">Exit $</th>
                  <th className="text-right py-1 pr-3">P&L</th>
                  <th className="text-left py-1">Reason</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.map((t, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="py-1 pr-3" style={{ color: "var(--text-muted)" }}>
                      {new Date(t.entry_ts).toLocaleDateString()}
                    </td>
                    <td className="py-1 pr-3" style={{ color: t.lean === "long" ? "var(--green)" : "var(--red)" }}>
                      {t.lean.toUpperCase()}
                    </td>
                    <td className="text-right py-1 pr-3">{t.entry_price.toFixed(2)}</td>
                    <td className="text-right py-1 pr-3">{t.exit_price.toFixed(2)}</td>
                    <td
                      className="text-right py-1 pr-3 font-semibold"
                      style={{ color: t.net_pnl >= 0 ? "var(--green)" : "var(--red)" }}
                    >
                      {`$${t.net_pnl.toFixed(2)}`}
                    </td>
                    <td className="py-1 text-xs" style={{ color: "var(--text-muted)" }}>{t.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricTile({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div
      className="rounded-lg px-3 py-2"
      style={{ background: "var(--bg)", border: "1px solid var(--border)" }}
    >
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="font-semibold text-sm" style={{ color: color ?? "var(--text)" }}>{value}</div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

function StrategyPage() {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <Activity size={18} style={{ color: "var(--accent)" }} />
        <h1 className="text-lg font-semibold">Strategy</h1>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StrategyConfigCard />
        <div className="sm:col-span-2">
          <BacktestRunner />
        </div>
      </div>
    </div>
  );
}
