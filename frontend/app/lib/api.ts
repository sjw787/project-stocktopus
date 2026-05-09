/** Thin fetch wrapper for the Stocktopus FastAPI backend. */

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: body != null ? { "Content-Type": "application/json" } : {},
    body: body != null ? JSON.stringify(body) : undefined,
  });
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

export interface StrategyConfig {
  symbol: string;
  timeframe: string;
  entry_time: string;
  exit_time: string;
  max_daily_trades: number;
  position_size_pct: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  require_regime?: string | null;
  min_llm_confidence?: number | null;
}

export interface BacktestRequest {
  symbol: string;
  start: string;
  end: string;
  timeframe?: string;
}

export interface BacktestMetrics {
  total_trades: number;
  win_rate: number;
  net_profit: number;
  max_drawdown: number;
  sharpe_ratio: number | null;
  profit_factor: number | null;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
}

export interface BacktestResult {
  metrics: BacktestMetrics;
  html_report: string | null;
  trades: BacktestTrade[];
}

export interface BacktestTrade {
  entry_ts: string;
  exit_ts: string;
  lean: string;
  entry_price: number;
  exit_price: number;
  net_pnl: number;
  exit_reason: string;
}

export interface PaperStatus {
  trades_completed: number;
  regimes_seen: number;
  phase8_gate: boolean;
  open_positions: number;
  daily_pnl: number;
  total_pnl: number;
  kill_switch_active: boolean;
}

export interface PaperDrift {
  checked_at: string;
  alarm_active: boolean;
  alarm_reasons: string[];
  n_trades: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number | null;
  expectancy: number;
  regimes_seen: string[];
  thresholds: { min_win_rate: number; min_profit_factor: number; lookback_days: number };
}

export interface PaperTrade {
  id: string;
  symbol: string;
  direction: string;
  qty: number;
  entry_price: number;
  exit_price: number | null;
  realized_pnl: number | null;
  regime: string | null;
  entry_ts: string;
  exit_ts: string | null;
  status: string;
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

  // Strategy
  strategyConfig: () => get<StrategyConfig>("/api/strategy/config"),

  // Backtest
  runBacktest: (req: BacktestRequest) =>
    post<BacktestResult>("/api/strategy/backtest", req),

  // Paper trading
  paperStatus: () => get<PaperStatus>("/api/paper/status"),
  paperTick: () => post<unknown>("/api/paper/tick"),
  paperKill: (symbol?: string) =>
    post<unknown>(`/api/paper/kill${symbol ? `?symbol=${symbol}` : ""}`),
  paperDrift: () => get<PaperDrift>("/api/paper/drift"),
  paperTrades: (limit = 50) =>
    get<PaperTrade[]>(`/api/paper/trades?limit=${limit}`),
};
