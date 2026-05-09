import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Activity, TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, XCircle, RefreshCw, } from "lucide-react";
import { api } from "~/lib/api";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, } from "recharts";
export const Route = createFileRoute("/")({
    component: Dashboard,
});
// ── Shared card shell ─────────────────────────────────────────────────────────
function Card({ title, children, className = "", }) {
    return (_jsxs("div", { className: `rounded-xl p-4 ${className}`, style: {
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
        }, children: [_jsx("h2", { className: "text-xs font-semibold uppercase tracking-widest mb-3", style: { color: "var(--text-muted)" }, children: title }), children] }));
}
// ── Health card ───────────────────────────────────────────────────────────────
function HealthCard() {
    const { data, isLoading, isError, refetch } = useQuery({
        queryKey: ["health"],
        queryFn: api.health,
        refetchInterval: 30_000,
    });
    return (_jsx(Card, { title: "System Health", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center gap-2", children: [isLoading ? (_jsx(RefreshCw, { size: 16, className: "animate-spin", style: { color: "var(--text-muted)" } })) : isError ? (_jsx(XCircle, { size: 16, style: { color: "var(--red)" } })) : (_jsx(CheckCircle, { size: 16, style: { color: "var(--green)" } })), _jsx("span", { className: "text-sm", children: isLoading ? "Checking…" : isError ? "Backend unreachable" : data?.status })] }), data && (_jsxs("span", { className: "text-xs", style: { color: "var(--text-muted)" }, children: [data.env, " \u00B7 v", data.version] })), _jsx("button", { onClick: () => void refetch(), style: { color: "var(--text-muted)" }, className: "ml-2 hover:opacity-70 transition-opacity", children: _jsx(RefreshCw, { size: 14 }) })] }) }));
}
// ── Regime / context card ─────────────────────────────────────────────────────
function RegimeCard() {
    const { data, isLoading, isError } = useQuery({
        queryKey: ["context"],
        queryFn: api.context,
        refetchInterval: 60_000,
    });
    const trend = data?.spy_trend_1d;
    return (_jsx(Card, { title: "Market Regime", children: isLoading ? (_jsx(Spinner, {})) : isError || !data ? (_jsx(EmptyState, { message: "No context snapshot available" })) : (_jsxs("div", { className: "space-y-3", children: [_jsxs("div", { className: "grid grid-cols-2 gap-2 sm:grid-cols-4", children: [_jsx(Stat, { label: "SPY", value: fmt(data.spy_price) }), _jsx(Stat, { label: "QQQ", value: fmt(data.qqq_price) }), _jsx(Stat, { label: "IWM", value: fmt(data.iwm_price) }), _jsx(Stat, { label: "VIX", value: fmt(data.vix), highlight: data.vix != null
                                ? data.vix > 25
                                    ? "red"
                                    : data.vix > 18
                                        ? "yellow"
                                        : "green"
                                : undefined })] }), _jsxs("div", { className: "grid grid-cols-2 gap-2 sm:grid-cols-4", children: [_jsx(Stat, { label: "gap %", value: data.spy_gap_pct != null ? `${data.spy_gap_pct.toFixed(2)}%` : "—", highlight: gapColor(data.spy_gap_pct) }), _jsx(Stat, { label: "XLK", value: fmt(data.xlk) }), _jsx(Stat, { label: "XLF", value: fmt(data.xlf) }), _jsx(Stat, { label: "XLE", value: fmt(data.xle) })] }), _jsxs("div", { className: "flex items-center gap-2 text-xs", style: { color: "var(--text-muted)" }, children: [_jsx(TrendIcon, { trend: trend }), _jsx("span", { children: trend ? `Trend: ${trend}` : "Trend data pending (Phase 4)" }), data.spy_above_vwap != null && (_jsxs("span", { children: ["\u00B7 ", data.spy_above_vwap ? "Above VWAP" : "Below VWAP"] })), _jsx("span", { className: "ml-auto", children: fmtTs(data.ts) })] })] })) }));
}
function gapColor(gap) {
    if (gap == null)
        return undefined;
    return gap > 0 ? "green" : gap < 0 ? "red" : undefined;
}
function TrendIcon({ trend }) {
    if (trend === "up")
        return _jsx(TrendingUp, { size: 14, style: { color: "var(--green)" } });
    if (trend === "down")
        return _jsx(TrendingDown, { size: 14, style: { color: "var(--red)" } });
    return _jsx(Minus, { size: 14, style: { color: "var(--text-muted)" } });
}
// ── Candle chart ──────────────────────────────────────────────────────────────
function CandleChart() {
    const { data, isLoading, isError } = useQuery({
        queryKey: ["candles", "SPY", "5m"],
        queryFn: () => api.candles("SPY", "5m", 78),
        refetchInterval: 60_000,
    });
    return (_jsx(Card, { title: "SPY \u00B7 5m \u00B7 last session", className: "col-span-full sm:col-span-2", children: isLoading ? (_jsx("div", { className: "h-48 flex items-center justify-center", children: _jsx(Spinner, {}) })) : isError || !data?.length ? (_jsx("div", { className: "h-48 flex items-center justify-center", children: _jsx(EmptyState, { message: "No candle data \u2014 run backfill first" }) })) : (_jsx(CandleAreaChart, { candles: data })) }));
}
function CandleAreaChart({ candles }) {
    const chartData = candles.map((c) => ({
        time: new Date(c.ts).toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        }),
        close: c.close,
        volume: c.volume,
    }));
    const first = chartData[0]?.close ?? 0;
    const last = chartData[chartData.length - 1]?.close ?? 0;
    const color = last >= first ? "var(--green)" : "var(--red)";
    return (_jsxs("div", { className: "space-y-1", children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx("span", { className: "text-xl font-semibold", children: last.toFixed(2) }), _jsxs("span", { className: "text-sm", style: { color: last >= first ? "var(--green)" : "var(--red)" }, children: [last >= first ? "+" : "", ((last - first) / first * 100).toFixed(2), "%"] })] }), _jsx(ResponsiveContainer, { width: "100%", height: 160, children: _jsxs(AreaChart, { data: chartData, margin: { top: 4, right: 0, left: 0, bottom: 0 }, children: [_jsx("defs", { children: _jsxs("linearGradient", { id: "fillClose", x1: "0", y1: "0", x2: "0", y2: "1", children: [_jsx("stop", { offset: "5%", stopColor: color, stopOpacity: 0.3 }), _jsx("stop", { offset: "95%", stopColor: color, stopOpacity: 0 })] }) }), _jsx(XAxis, { dataKey: "time", tick: { fill: "var(--text-muted)", fontSize: 10 }, tickLine: false, axisLine: false, interval: "preserveStartEnd" }), _jsx(YAxis, { domain: ["auto", "auto"], tick: { fill: "var(--text-muted)", fontSize: 10 }, tickLine: false, axisLine: false, width: 55, tickFormatter: (v) => v.toFixed(1) }), _jsx(Tooltip, { contentStyle: {
                                background: "var(--bg-card)",
                                border: "1px solid var(--border)",
                                borderRadius: 8,
                                fontSize: 12,
                            }, labelStyle: { color: "var(--text-muted)" }, itemStyle: { color: "var(--text)" } }), _jsx(Area, { type: "monotone", dataKey: "close", stroke: color, strokeWidth: 1.5, fill: "url(#fillClose)", dot: false, activeDot: { r: 3 } })] }) })] }));
}
// ── Latest candles table ──────────────────────────────────────────────────────
function CandleTable() {
    const { data, isLoading, isError } = useQuery({
        queryKey: ["candles", "SPY", "1m"],
        queryFn: () => api.candles("SPY", "1m", 20),
        refetchInterval: 60_000,
    });
    return (_jsx(Card, { title: "SPY \u00B7 1m \u00B7 latest bars", children: isLoading ? (_jsx(Spinner, {})) : isError || !data?.length ? (_jsx(EmptyState, { message: "No candle data \u2014 run backfill first" })) : (_jsxs("table", { className: "w-full text-xs", style: { borderCollapse: "collapse" }, children: [_jsx("thead", { children: _jsxs("tr", { style: { color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }, children: [_jsx("th", { className: "text-left py-1 pr-3", children: "Time" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Open" }), _jsx("th", { className: "text-right py-1 pr-3", children: "High" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Low" }), _jsx("th", { className: "text-right py-1 pr-3", children: "Close" }), _jsx("th", { className: "text-right py-1", children: "Volume" })] }) }), _jsx("tbody", { children: [...data].reverse().map((c) => (_jsxs("tr", { style: { borderBottom: "1px solid var(--border)" }, className: "hover:opacity-80 transition-opacity", children: [_jsx("td", { className: "py-1 pr-3", style: { color: "var(--text-muted)" }, children: new Date(c.ts).toLocaleTimeString("en-US", {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                    hour12: false,
                                }) }), _jsx("td", { className: "text-right py-1 pr-3", children: c.open.toFixed(2) }), _jsx("td", { className: "text-right py-1 pr-3", style: { color: "var(--green)" }, children: c.high.toFixed(2) }), _jsx("td", { className: "text-right py-1 pr-3", style: { color: "var(--red)" }, children: c.low.toFixed(2) }), _jsx("td", { className: "text-right py-1 pr-3 font-semibold", style: { color: c.close >= c.open ? "var(--green)" : "var(--red)" }, children: c.close.toFixed(2) }), _jsxs("td", { className: "text-right py-1", style: { color: "var(--text-muted)" }, children: [(c.volume / 1_000).toFixed(0), "K"] })] }, c.ts))) })] })) }));
}
// ── Main layout ───────────────────────────────────────────────────────────────
function Dashboard() {
    return (_jsxs("div", { className: "space-y-4", children: [_jsxs("div", { className: "flex items-center gap-2 mb-2", children: [_jsx(Activity, { size: 18, style: { color: "var(--accent)" } }), _jsx("h1", { className: "text-lg font-semibold", children: "Dashboard" })] }), _jsx(HealthCard, {}), _jsxs("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-4", children: [_jsx(RegimeCard, {}), _jsx(CandleChart, {})] }), _jsx(CandleTable, {})] }));
}
// ── Shared micro-components ───────────────────────────────────────────────────
function Stat({ label, value, highlight, }) {
    const color = highlight
        ? `var(--${highlight})`
        : "var(--text)";
    return (_jsxs("div", { className: "rounded-lg px-3 py-2", style: { background: "var(--bg)", border: "1px solid var(--border)" }, children: [_jsx("div", { className: "text-xs", style: { color: "var(--text-muted)" }, children: label }), _jsx("div", { className: "font-semibold text-sm", style: { color }, children: value })] }));
}
function Spinner() {
    return (_jsx("div", { className: "flex justify-center py-4", children: _jsx(RefreshCw, { size: 18, className: "animate-spin", style: { color: "var(--text-muted)" } }) }));
}
function EmptyState({ message }) {
    return (_jsxs("div", { className: "flex items-center gap-2 py-4 text-sm", style: { color: "var(--text-muted)" }, children: [_jsx(AlertTriangle, { size: 14 }), message] }));
}
function fmt(n) {
    return n != null ? n.toFixed(2) : "—";
}
function fmtTs(ts) {
    return new Date(ts).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    });
}
