/** Thin fetch wrapper for the Stocktopus FastAPI backend. */

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
  env: string;
}

export interface Candle {
  symbol: string;
  timeframe: string;
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number | null;
}

export interface NewsItem {
  id: string;
  headline: string;
  summary?: string | null;
  source: string;
  url: string;
  published_at: string;
  symbols: string[];
  categories: string[];
  sentiment_score?: number | null;
}

export interface MarketContext {
  ts: string;
  vix?: number | null;
  spy_price?: number | null;
  spy_gap_pct?: number | null;
  qqq_price?: number | null;
  iwm_price?: number | null;
  dia_price?: number | null;
  xlk?: number | null;
  xlf?: number | null;
  xle?: number | null;
  xlv?: number | null;
  xli?: number | null;
  spy_above_vwap?: boolean | null;
  spy_trend_1d?: string | null;
}

// ── API calls ────────────────────────────────────────────────────────────────

export const api = {
  health: () => get<HealthResponse>("/health"),

  candles: (symbol: string, timeframe: string, limit = 50) =>
    get<Candle[]>(
      `/api/candles?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`
    ),

  news: (limit = 20) => get<NewsItem[]>(`/api/news?limit=${limit}`),

  context: () => get<MarketContext | null>("/api/context/latest"),
};
