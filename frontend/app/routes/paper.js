import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle, RefreshCw, Zap, ZapOff } from "lucide-react";
import { api } from "~/lib/api";
export const Route = createFileRoute("/paper")({
    component: PaperPage,
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
// ── Status card ───────────────────────────────────────────────────────────────
function StatusCard() {
    const qc = useQueryClient();
    const { data, isLoading, isError } = useQuery({
        queryKey: ["paper-status"],
        queryFn: api.paperStatus,
        refetchInterval: 30_000,
    });
    const tick = useMutation({
        mutationFn: api.paperTick,
        onSuccess: () => void qc.invalidateQueries({ queryKey: ["paper-status"] }),
    });
    const kill = useMutation({
        mutationFn: () => api.paperKill(),
        onSuccess: () => void qc.invalidateQueries({ queryKey: ["paper-status"] }),
    });
    return (_jsx(Card, { title: "Paper Trading Status", children: isLoading ? (_jsx(Spinner, {})) : isError || !data ? (_jsx(EmptyState, { message: "Backend unreachable" })) : (_jsxs("div", { className: "space-y-4", children: [_jsxs("div", { children: [_jsxs("div", { className: "flex justify-between text-xs mb-1", style: { color: "var(--text-muted)" }, children: [_jsx("span", { children: "Phase 8 gate" }), _jsxs("span", { children: [data.trades_completed, "/100 trades \u00B7 ", data.regimes_seen, "/3 regimes"] })] }), _jsx("div", { className: "rounded-full h-2 overflow-hidden", style: { background: "var(--border)" }, children: _jsx("div", { className: "h-full rounded-full transition-all", style: {
                                    width: `${Math.min(100, data.trades_completed)}%`,
                                    background: data.phase8_gate ? "var(--green)" : "var(--accent)",
                                } }) }), data.phase8_gate && (_jsxs("div", { className: "flex items-center gap-1 mt-1 text-xs", style: { color: "var(--green)" }, children: [_jsx(CheckCircle, { size: 12 }), "Gate cleared \u2014 ready for Phase 9"] }))] }), _jsxs("div", { className: "grid grid-cols-2 gap-2", children: [_jsx(StatTile, { label: "Today P&L", value: `$${data.daily_pnl.toFixed(2)}`, color: data.daily_pnl >= 0 ? "var(--green)" : "var(--red)" }), _jsx(StatTile, { label: "Total P&L", value: `$${data.total_pnl.toFixed(2)}`, color: data.total_pnl >= 0 ? "var(--green)" : "var(--red)" }), _jsx(StatTile, { label: "Open Positions", value: String(data.open_positions) }), _jsx(StatTile, { label: "Kill Switch", value: data.kill_switch_active ? "ACTIVE" : "off", color: data.kill_switch_active ? "var(--red)" : undefined })] }), _jsxs("div", { className: "flex gap-2", children: [_jsxs("button", { onClick: () => tick.mutate(), disabled: tick.isPending || data.kill_switch_active, className: "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80 disabled:opacity-40", style: { background: "var(--accent)", color: "#fff" }, children: [tick.isPending ? _jsx(RefreshCw, { size: 13, className: "animate-spin" }) : _jsx(Zap, { size: 13 }), "Tick"] }), _jsxs("button", { onClick: () => kill.mutate(), disabled: kill.isPending, className: "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80 disabled:opacity-40", style: { background: "var(--red)", color: "#fff" }, children: [kill.isPending ? _jsx(RefreshCw, { size: 13, className: "animate-spin" }) : _jsx(ZapOff, { size: 13 }), "Kill All"] })] })] })) }));
}
// ── Drift alarm card ──────────────────────────────────────────────────────────
function DriftCard() {
    const { data, isLoading, isError } = useQuery({
        queryKey: ["paper-drift"],
        queryFn: api.paperDrift,
        refetchInterval: 60_000,
    });
    return (_jsx(Card, { title: "Drift Alarm", children: isLoading ? (_jsx(Spinner, {})) : isError || !data ? (_jsx(EmptyState, { message: "No drift data available" })) : (_jsxs("div", { className: "space-y-3", children: [_jsx("div", { className: "flex items-center gap-2", children: data.alarm_active ? (_jsxs(_Fragment, { children: [_jsx(AlertTriangle, { size: 16, style: { color: "var(--red)" } }), _jsx("span", { className: "text-sm font-semibold", style: { color: "var(--red)" }, children: "ALARM ACTIVE" })] })) : (_jsxs(_Fragment, { children: [_jsx(CheckCircle, { size: 16, style: { color: "var(--green)" } }), _jsx("span", { className: "text-sm font-semibold", style: { color: "var(--green)" }, children: "Distribution healthy" })] })) }), data.alarm_reasons.length > 0 && (_jsx("ul", { className: "space-y-1", children: data.alarm_reasons.map((r, i) => (_jsxs("li", { className: "text-xs", style: { color: "var(--red)" }, children: ["\u00B7 ", r] }, i))) })), _jsxs("div", { className: "grid grid-cols-2 gap-2", children: [_jsx(StatTile, { label: "Trades sampled", value: String(data.n_trades) }), _jsx(StatTile, { label: "Win rate", value: `${(data.win_rate * 100).toFixed(1)}%` }), _jsx(StatTile, { label: "Profit factor", value: data.profit_factor?.toFixed(2) ?? "∞" }), _jsx(StatTile, { label: "Expectancy", value: `$${data.expectancy.toFixed(2)}` })] }), _jsxs("div", { className: "text-xs", style: { color: "var(--text-muted)" }, children: ["Regimes: ", data.regimes_seen.join(", ") || "—"] }), _jsxs("div", { className: "text-xs", style: { color: "var(--text-muted)" }, children: ["Checked ", new Date(data.checked_at).toLocaleString()] })] })) }));
}
// ── Trade journal ─────────────────────────────────────────────────────────────
function TradeJournal() {
    const { data, isLoading, isError } = useQuery({
        queryKey: ["paper-trades"],
        queryFn: () => api.paperTrades(),
        refetchInterval: 30_000,
    });
    return (_jsx(Card, { title: "Trade Journal", className: "col-span-full", children: isLoading ? (_jsx(Spinner, {})) : isError || !data?.length ? (_jsx(EmptyState, { message: "No paper trades yet \u2014 run a tick to start" })) : (_jsx("div", { style: { overflowX: "auto" }, children: _jsxs("table", { className: "w-full text-xs", style: { borderCollapse: "collapse" }, children: [_jsx("thead", { children: _jsxs("tr", { style: { color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }, children: [_jsx("th", { className: "text-left py-1 pr-3", children: "Entry" }), _jsx("th", { className: "text-left py-1 pr-3", children: "Symbol" }), _jsx("th", { className: "text-left py-1 pr-3", children: "Dir" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Qty" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Entry $" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Exit $" }), _jsx("th", { className: "text-right py-1 pr-3", children: "P&L" }), _jsx("th", { className: "text-left py-1 pr-3", children: "Regime" }), _jsx("th", { className: "text-left py-1", children: "Status" })] }) }), _jsx("tbody", { children: data.map((t) => (_jsxs("tr", { style: { borderBottom: "1px solid var(--border)" }, className: "hover:opacity-80 transition-opacity", children: [_jsx("td", { className: "py-1 pr-3", style: { color: "var(--text-muted)" }, children: new Date(t.entry_ts).toLocaleDateString() }), _jsx("td", { className: "py-1 pr-3 font-semibold", children: t.symbol }), _jsx("td", { className: "py-1 pr-3 font-semibold", style: { color: t.direction === "long" ? "var(--green)" : "var(--red)" }, children: t.direction.toUpperCase() }), _jsx("td", { className: "text-right py-1 pr-3", children: t.qty }), _jsx("td", { className: "text-right py-1 pr-3", children: t.entry_price.toFixed(2) }), _jsx("td", { className: "text-right py-1 pr-3", children: t.exit_price?.toFixed(2) ?? "—" }), _jsx("td", { className: "text-right py-1 pr-3 font-semibold", style: { color: (t.realized_pnl ?? 0) >= 0 ? "var(--green)" : "var(--red)" }, children: t.realized_pnl != null ? `$${t.realized_pnl.toFixed(2)}` : "—" }), _jsx("td", { className: "py-1 pr-3", style: { color: "var(--text-muted)" }, children: t.regime ?? "—" }), _jsx("td", { className: "py-1", children: _jsx("span", { className: "rounded-full px-2 py-0.5 text-xs", style: {
                                            background: t.status === "open" ? "var(--accent)" : "var(--border)",
                                            color: t.status === "open" ? "#fff" : "var(--text-muted)",
                                        }, children: t.status }) })] }, t.id))) })] }) })) }));
}
// ── Stat tile ─────────────────────────────────────────────────────────────────
function StatTile({ label, value, color }) {
    return (_jsxs("div", { className: "rounded-lg px-3 py-2", style: { background: "var(--bg)", border: "1px solid var(--border)" }, children: [_jsx("div", { className: "text-xs", style: { color: "var(--text-muted)" }, children: label }), _jsx("div", { className: "font-semibold text-sm", style: { color: color ?? "var(--text)" }, children: value })] }));
}
// ── Page ──────────────────────────────────────────────────────────────────────
function PaperPage() {
    return (_jsxs("div", { className: "space-y-4", children: [_jsxs("div", { className: "flex items-center gap-2 mb-2", children: [_jsx(Zap, { size: 18, style: { color: "var(--accent)" } }), _jsx("h1", { className: "text-lg font-semibold", children: "Paper Trading" })] }), _jsxs("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-4", children: [_jsx(StatusCard, {}), _jsx(DriftCard, {})] }), _jsx("div", { className: "grid grid-cols-1 gap-4", children: _jsx(TradeJournal, {}) })] }));
}
