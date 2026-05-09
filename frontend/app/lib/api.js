/** Thin fetch wrapper for the Stocktopus FastAPI backend. */
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
async function get(path) {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok)
        throw new Error(`${res.status} ${res.statusText} — ${path}`);
    return res.json();
}
async function post(path, body) {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: body != null ? { "Content-Type": "application/json" } : {},
        body: body != null ? JSON.stringify(body) : undefined,
    });
    if (!res.ok)
        throw new Error(`${res.status} ${res.statusText} — ${path}`);
    return res.json();
}
// ── API calls ────────────────────────────────────────────────────────────────
export const api = {
    health: () => get("/health"),
    candles: (symbol, timeframe, limit = 50) => get(`/api/candles?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`),
    news: (limit = 20) => get(`/api/news?limit=${limit}`),
    context: () => get("/api/context/latest"),
    // Strategy
    strategyConfig: () => get("/api/strategy/config"),
    // Backtest
    runBacktest: (req) => post("/api/strategy/backtest", req),
    // Paper trading
    paperStatus: () => get("/api/paper/status"),
    paperTick: () => post("/api/paper/tick"),
    paperKill: (symbol) => post(`/api/paper/kill${symbol ? `?symbol=${symbol}` : ""}`),
    paperDrift: () => get("/api/paper/drift"),
    paperTrades: (limit = 50) => get(`/api/paper/trades?limit=${limit}`),
};
