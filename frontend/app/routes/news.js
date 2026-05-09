import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Newspaper, RefreshCw, AlertTriangle, ExternalLink } from "lucide-react";
import { api } from "~/lib/api";
export const Route = createFileRoute("/news")({
    component: NewsPage,
});
function NewsPage() {
    const { data, isLoading, isError, refetch, isFetching } = useQuery({
        queryKey: ["news"],
        queryFn: () => api.news(40),
        refetchInterval: 120_000,
    });
    return (_jsxs("div", { className: "space-y-4", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx(Newspaper, { size: 18, style: { color: "var(--accent)" } }), _jsx("h1", { className: "text-lg font-semibold", children: "News Feed" })] }), _jsxs("button", { onClick: () => void refetch(), className: "flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg transition-opacity hover:opacity-70", style: {
                            background: "var(--bg-card)",
                            border: "1px solid var(--border)",
                            color: "var(--text-muted)",
                        }, children: [_jsx(RefreshCw, { size: 12, className: isFetching ? "animate-spin" : "" }), "Refresh"] })] }), isLoading ? (_jsx(LoadingRows, {})) : isError ? (_jsx(ErrorState, {})) : !data?.length ? (_jsx(EmptyState, {})) : (_jsx(NewsList, { items: data }))] }));
}
function NewsList({ items }) {
    return (_jsx("div", { className: "space-y-2", children: items.map((item) => (_jsx(NewsCard, { item: item }, item.id))) }));
}
function NewsCard({ item }) {
    const score = item.sentiment_score;
    const sentimentColor = score == null
        ? "var(--text-muted)"
        : score > 0.1
            ? "var(--green)"
            : score < -0.1
                ? "var(--red)"
                : "var(--yellow)";
    return (_jsx("div", { className: "rounded-xl p-4 hover:opacity-90 transition-opacity", style: {
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
        }, children: _jsxs("div", { className: "flex items-start justify-between gap-3", children: [_jsxs("div", { className: "flex-1 min-w-0", children: [_jsxs("a", { href: item.url, target: "_blank", rel: "noopener noreferrer", className: "text-sm font-medium hover:underline flex items-start gap-1", children: [item.headline, _jsx(ExternalLink, { size: 10, className: "mt-1 flex-shrink-0", style: { color: "var(--text-muted)" } })] }), item.summary && (_jsx("p", { className: "text-xs mt-1 line-clamp-2", style: { color: "var(--text-muted)" }, children: item.summary })), _jsxs("div", { className: "flex flex-wrap items-center gap-2 mt-2", children: [_jsx("span", { className: "text-xs", style: { color: "var(--text-muted)" }, children: item.source }), _jsx("span", { className: "text-xs", style: { color: "var(--text-muted)" }, children: fmtDate(item.published_at) }), item.symbols.length > 0 && (_jsx("div", { className: "flex gap-1", children: item.symbols.slice(0, 3).map((s) => (_jsx("span", { className: "text-xs px-1.5 py-0.5 rounded", style: {
                                            background: "var(--accent-dim)",
                                            color: "var(--text)",
                                            opacity: 0.8,
                                        }, children: s }, s))) })), item.categories.length > 0 && (_jsx("div", { className: "flex gap-1", children: item.categories.map((c) => (_jsx("span", { className: "text-xs px-1.5 py-0.5 rounded", style: {
                                            background: "var(--bg)",
                                            border: "1px solid var(--border)",
                                            color: "var(--text-muted)",
                                        }, children: c }, c))) }))] })] }), score != null && (_jsxs("div", { className: "flex-shrink-0 text-right", children: [_jsxs("div", { className: "text-xs font-semibold", style: { color: sentimentColor }, children: [score > 0 ? "+" : "", score.toFixed(2)] }), _jsx("div", { className: "text-xs", style: { color: "var(--text-muted)" }, children: "sentiment" })] }))] }) }));
}
function LoadingRows() {
    return (_jsx("div", { className: "space-y-2", children: Array.from({ length: 6 }).map((_, i) => (_jsx("div", { className: "h-20 rounded-xl animate-pulse", style: { background: "var(--bg-card)", border: "1px solid var(--border)" } }, i))) }));
}
function ErrorState() {
    return (_jsxs("div", { className: "rounded-xl p-6 flex items-center gap-2", style: {
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            color: "var(--red)",
        }, children: [_jsx(AlertTriangle, { size: 16 }), _jsx("span", { className: "text-sm", children: "Failed to load news \u2014 is the backend running?" })] }));
}
function EmptyState() {
    return (_jsxs("div", { className: "rounded-xl p-6 flex items-center gap-2", style: {
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            color: "var(--text-muted)",
        }, children: [_jsx(Newspaper, { size: 16 }), _jsx("span", { className: "text-sm", children: "No news yet \u2014 run the news ingestion job first." })] }));
}
function fmtDate(iso) {
    return new Date(iso).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    });
}
