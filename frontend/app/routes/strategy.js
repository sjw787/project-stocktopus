import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Activity, AlertTriangle, PlayCircle, RefreshCw } from "lucide-react";
import { api } from "~/lib/api";
export const Route = createFileRoute("/strategy")({
    component: StrategyPage,
});
// ── Shared micro-components ───────────────────────────────────────────────────
function Card({ title, children, className = "", }) {
    return (_jsxs("div", { className: `rounded-xl p-4 ${className}`, style: { background: "var(--bg-card)", border: "1px solid var(--border)" }, children: [_jsx("h2", { className: "text-xs font-semibold uppercase tracking-widest mb-3", style: { color: "var(--text-muted)" }, children: title }), children] }));
}
function Spinner() {
    return (_jsx("div", { className: "flex justify-center py-4", children: _jsx(RefreshCw, { size: 18, className: "animate-spin", style: { color: "var(--text-muted)" } }) }));
}
function EmptyState({ message }) {
    return (_jsxs("div", { className: "flex items-center gap-2 py-4 text-sm", style: { color: "var(--text-muted)" }, children: [_jsx(AlertTriangle, { size: 14 }), message] }));
}
function Row({ label, value }) {
    return (_jsxs("div", { className: "flex justify-between items-center py-1.5", style: { borderBottom: "1px solid var(--border)" }, children: [_jsx("span", { className: "text-xs", style: { color: "var(--text-muted)" }, children: label }), _jsx("span", { className: "text-xs font-semibold", children: value ?? "—" })] }));
}
// ── Strategy config card ──────────────────────────────────────────────────────
function StrategyConfigCard() {
    const { data, isLoading, isError } = useQuery({
        queryKey: ["strategy-config"],
        queryFn: api.strategyConfig,
    });
    return (_jsx(Card, { title: "Strategy Configuration", children: isLoading ? (_jsx(Spinner, {})) : isError || !data ? (_jsx(EmptyState, { message: "Could not load strategy config" })) : (_jsxs("div", { children: [_jsx(Row, { label: "Symbol", value: data.symbol }), _jsx(Row, { label: "Timeframe", value: data.timeframe }), _jsx(Row, { label: "Entry window", value: data.entry_time }), _jsx(Row, { label: "Exit window", value: data.exit_time }), _jsx(Row, { label: "Max daily trades", value: data.max_daily_trades }), _jsx(Row, { label: "Position size", value: `${data.position_size_pct.toFixed(1)}%` }), _jsx(Row, { label: "Stop loss", value: `${data.stop_loss_pct}%` }), _jsx(Row, { label: "Take profit", value: `${data.take_profit_pct}%` }), _jsx(Row, { label: "Required regime", value: data.require_regime ?? "any" }), _jsx(Row, { label: "Min LLM confidence", value: data.min_llm_confidence ?? "none" })] })) }));
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
    const mutation = useMutation({
        mutationFn: () => api.runBacktest({ symbol: "SPY", start, end, timeframe: "5m" }),
    });
    return (_jsxs(Card, { title: "Run Backtest", children: [_jsxs("div", { className: "flex flex-wrap gap-3 mb-4 items-end", children: [_jsxs("label", { className: "flex flex-col gap-1 text-xs", style: { color: "var(--text-muted)" }, children: ["Start", _jsx("input", { type: "date", value: start, onChange: (e) => setStart(e.target.value), style: {
                                    background: "var(--bg)",
                                    border: "1px solid var(--border)",
                                    borderRadius: 6,
                                    padding: "4px 8px",
                                    color: "var(--text)",
                                    fontSize: 12,
                                } })] }), _jsxs("label", { className: "flex flex-col gap-1 text-xs", style: { color: "var(--text-muted)" }, children: ["End", _jsx("input", { type: "date", value: end, onChange: (e) => setEnd(e.target.value), style: {
                                    background: "var(--bg)",
                                    border: "1px solid var(--border)",
                                    borderRadius: 6,
                                    padding: "4px 8px",
                                    color: "var(--text)",
                                    fontSize: 12,
                                } })] }), _jsxs("button", { onClick: () => mutation.mutate(), disabled: mutation.isPending, className: "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80", style: { background: "var(--accent)", color: "#fff" }, children: [mutation.isPending ? (_jsx(RefreshCw, { size: 14, className: "animate-spin" })) : (_jsx(PlayCircle, { size: 14 })), "Run"] })] }), mutation.isError && (_jsxs("div", { className: "text-sm mb-3", style: { color: "var(--red)" }, children: ["Error: ", mutation.error.message] })), mutation.data && _jsx(BacktestResults, { result: mutation.data })] }));
}
// ── Backtest results ──────────────────────────────────────────────────────────
function BacktestResults({ result }) {
    const m = result.metrics;
    const pnlColor = m.net_profit >= 0 ? "var(--green)" : "var(--red)";
    return (_jsxs("div", { className: "space-y-4", children: [_jsxs("div", { className: "grid grid-cols-2 sm:grid-cols-4 gap-2", children: [_jsx(MetricTile, { label: "Net P&L", value: `$${m.net_profit.toFixed(2)}`, color: pnlColor }), _jsx(MetricTile, { label: "Win Rate", value: `${(m.win_rate * 100).toFixed(1)}%` }), _jsx(MetricTile, { label: "Profit Factor", value: m.profit_factor?.toFixed(2) ?? "—" }), _jsx(MetricTile, { label: "Total Trades", value: String(m.total_trades) }), _jsx(MetricTile, { label: "Max Drawdown", value: `${(m.max_drawdown * 100).toFixed(2)}%`, color: "var(--red)" }), _jsx(MetricTile, { label: "Sharpe", value: m.sharpe_ratio?.toFixed(2) ?? "—" }), _jsx(MetricTile, { label: "Avg Win", value: `$${m.avg_win.toFixed(2)}`, color: "var(--green)" }), _jsx(MetricTile, { label: "Avg Loss", value: `$${m.avg_loss.toFixed(2)}`, color: "var(--red)" })] }), result.trades.length > 0 && (_jsxs("div", { children: [_jsxs("h3", { className: "text-xs font-semibold uppercase tracking-widest mb-2", style: { color: "var(--text-muted)" }, children: ["Trades (", result.trades.length, ")"] }), _jsx("div", { style: { overflowX: "auto" }, children: _jsxs("table", { className: "w-full text-xs", style: { borderCollapse: "collapse" }, children: [_jsx("thead", { children: _jsxs("tr", { style: { color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }, children: [_jsx("th", { className: "text-left py-1 pr-3", children: "Entry" }), _jsx("th", { className: "text-left py-1 pr-3", children: "Dir" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Entry $" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Exit $" }), _jsx("th", { className: "text-right py-1 pr-3", children: "P&L" }), _jsx("th", { className: "text-left py-1", children: "Reason" })] }) }), _jsx("tbody", { children: result.trades.map((t, i) => (_jsxs("tr", { style: { borderBottom: "1px solid var(--border)" }, children: [_jsx("td", { className: "py-1 pr-3", style: { color: "var(--text-muted)" }, children: new Date(t.entry_ts).toLocaleDateString() }), _jsx("td", { className: "py-1 pr-3", style: { color: t.direction === "long" ? "var(--green)" : "var(--red)" }, children: t.direction.toUpperCase() }), _jsx("td", { className: "text-right py-1 pr-3", children: t.entry_price.toFixed(2) }), _jsx("td", { className: "text-right py-1 pr-3", children: t.exit_price?.toFixed(2) ?? "—" }), _jsx("td", { className: "text-right py-1 pr-3 font-semibold", style: { color: (t.pnl ?? 0) >= 0 ? "var(--green)" : "var(--red)" }, children: t.pnl != null ? `$${t.pnl.toFixed(2)}` : "—" }), _jsx("td", { className: "py-1 text-xs", style: { color: "var(--text-muted)" }, children: t.exit_reason })] }, i))) })] }) })] }))] }));
}
function MetricTile({ label, value, color, }) {
    return (_jsxs("div", { className: "rounded-lg px-3 py-2", style: { background: "var(--bg)", border: "1px solid var(--border)" }, children: [_jsx("div", { className: "text-xs", style: { color: "var(--text-muted)" }, children: label }), _jsx("div", { className: "font-semibold text-sm", style: { color: color ?? "var(--text)" }, children: value })] }));
}
// ── Page ──────────────────────────────────────────────────────────────────────
function StrategyPage() {
    return (_jsxs("div", { className: "space-y-4", children: [_jsxs("div", { className: "flex items-center gap-2 mb-2", children: [_jsx(Activity, { size: 18, style: { color: "var(--accent)" } }), _jsx("h1", { className: "text-lg font-semibold", children: "Strategy" })] }), _jsxs("div", { className: "grid grid-cols-1 sm:grid-cols-3 gap-4", children: [_jsx(StrategyConfigCard, {}), _jsx("div", { className: "sm:col-span-2", children: _jsx(BacktestRunner, {}) })] })] }));
}
