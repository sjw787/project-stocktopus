import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
} from "lucide-react";
import { api, type Candle, type MarketContext } from "~/lib/api";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export const Route = createFileRoute("/")({
  component: Dashboard,
});

// ── Shared card shell ─────────────────────────────────────────────────────────

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
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
      }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
        {title}
      </h2>
      {children}
    </div>
  );
}

// ── Health card ───────────────────────────────────────────────────────────────

function HealthCard() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });

  return (
    <Card title="System Health">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isLoading ? (
            <RefreshCw size={16} className="animate-spin" style={{ color: "var(--text-muted)" }} />
          ) : isError ? (
            <XCircle size={16} style={{ color: "var(--red)" }} />
          ) : (
            <CheckCircle size={16} style={{ color: "var(--green)" }} />
          )}
          <span className="text-sm">
            {isLoading ? "Checking…" : isError ? "Backend unreachable" : data?.status}
          </span>
        </div>
        {data && (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            {data.env} · v{data.version}
          </span>
        )}
        <button
          onClick={() => void refetch()}
          style={{ color: "var(--text-muted)" }}
          className="ml-2 hover:opacity-70 transition-opacity"
        >
          <RefreshCw size={14} />
        </button>
      </div>
    </Card>
  );
}

// ── Regime / context card ─────────────────────────────────────────────────────

function RegimeCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["context"],
    queryFn: api.context,
    refetchInterval: 60_000,
  });

  const trend = data?.spy_trend_1d;

  return (
    <Card title="Market Regime">
      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <EmptyState message="No context snapshot available" />
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="SPY" value={fmt(data.spy_price)} />
            <Stat label="QQQ" value={fmt(data.qqq_price)} />
            <Stat label="IWM" value={fmt(data.iwm_price)} />
            <Stat
              label="VIX"
              value={fmt(data.vix)}
              highlight={
                data.vix != null
                  ? data.vix > 25
                    ? "red"
                    : data.vix > 18
                      ? "yellow"
                      : "green"
                  : undefined
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="gap %" value={data.spy_gap_pct != null ? `${data.spy_gap_pct.toFixed(2)}%` : "—"} highlight={gapColor(data.spy_gap_pct)} />
            <Stat label="XLK" value={fmt(data.xlk)} />
            <Stat label="XLF" value={fmt(data.xlf)} />
            <Stat label="XLE" value={fmt(data.xle)} />
          </div>
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
            <TrendIcon trend={trend} />
            <span>
              {trend ? `Trend: ${trend}` : "Trend data pending (Phase 4)"}
            </span>
            {data.spy_above_vwap != null && (
              <span>· {data.spy_above_vwap ? "Above VWAP" : "Below VWAP"}</span>
            )}
            <span className="ml-auto">{fmtTs(data.ts)}</span>
          </div>
        </div>
      )}
    </Card>
  );
}

function gapColor(gap: number | null | undefined): "green" | "red" | undefined {
  if (gap == null) return undefined;
  return gap > 0 ? "green" : gap < 0 ? "red" : undefined;
}

function TrendIcon({ trend }: { trend?: string | null }) {
  if (trend === "up") return <TrendingUp size={14} style={{ color: "var(--green)" }} />;
  if (trend === "down") return <TrendingDown size={14} style={{ color: "var(--red)" }} />;
  return <Minus size={14} style={{ color: "var(--text-muted)" }} />;
}

// ── Candle chart ──────────────────────────────────────────────────────────────

function CandleChart() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["candles", "SPY", "5m"],
    queryFn: () => api.candles("SPY", "5m", 78),
    refetchInterval: 60_000,
  });

  return (
    <Card title="SPY · 5m · last session" className="col-span-full sm:col-span-2">
      {isLoading ? (
        <div className="h-48 flex items-center justify-center"><Spinner /></div>
      ) : isError || !data?.length ? (
        <div className="h-48 flex items-center justify-center">
          <EmptyState message="No candle data — run backfill first" />
        </div>
      ) : (
        <CandleAreaChart candles={data} />
      )}
    </Card>
  );
}

function CandleAreaChart({ candles }: { candles: Candle[] }) {
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

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-xl font-semibold">{last.toFixed(2)}</span>
        <span
          className="text-sm"
          style={{ color: last >= first ? "var(--green)" : "var(--red)" }}
        >
          {last >= first ? "+" : ""}
          {((last - first) / first * 100).toFixed(2)}%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={chartData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="fillClose" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            tick={{ fill: "var(--text-muted)", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: "var(--text-muted)", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={55}
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--text-muted)" }}
            itemStyle={{ color: "var(--text)" }}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={color}
            strokeWidth={1.5}
            fill="url(#fillClose)"
            dot={false}
            activeDot={{ r: 3 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Latest candles table ──────────────────────────────────────────────────────

function CandleTable() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["candles", "SPY", "1m"],
    queryFn: () => api.candles("SPY", "1m", 20),
    refetchInterval: 60_000,
  });

  return (
    <Card title="SPY · 1m · latest bars">
      {isLoading ? (
        <Spinner />
      ) : isError || !data?.length ? (
        <EmptyState message="No candle data — run backfill first" />
      ) : (
        <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
              <th className="text-left py-1 pr-3">Time</th>
              <th className="text-right py-1 pr-3">Open</th>
              <th className="text-right py-1 pr-3">High</th>
              <th className="text-right py-1 pr-3">Low</th>
              <th className="text-right py-1 pr-3">Close</th>
              <th className="text-right py-1">Volume</th>
            </tr>
          </thead>
          <tbody>
            {[...data].reverse().map((c) => (
              <tr
                key={c.ts}
                style={{ borderBottom: "1px solid var(--border)" }}
                className="hover:opacity-80 transition-opacity"
              >
                <td className="py-1 pr-3" style={{ color: "var(--text-muted)" }}>
                  {new Date(c.ts).toLocaleTimeString("en-US", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })}
                </td>
                <td className="text-right py-1 pr-3">{c.open.toFixed(2)}</td>
                <td className="text-right py-1 pr-3" style={{ color: "var(--green)" }}>
                  {c.high.toFixed(2)}
                </td>
                <td className="text-right py-1 pr-3" style={{ color: "var(--red)" }}>
                  {c.low.toFixed(2)}
                </td>
                <td
                  className="text-right py-1 pr-3 font-semibold"
                  style={{ color: c.close >= c.open ? "var(--green)" : "var(--red)" }}
                >
                  {c.close.toFixed(2)}
                </td>
                <td className="text-right py-1" style={{ color: "var(--text-muted)" }}>
                  {(c.volume / 1_000).toFixed(0)}K
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ── Main layout ───────────────────────────────────────────────────────────────

function Dashboard() {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <Activity size={18} style={{ color: "var(--accent)" }} />
        <h1 className="text-lg font-semibold">Dashboard</h1>
      </div>

      <HealthCard />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <RegimeCard />
        <CandleChart />
      </div>

      <CandleTable />
    </div>
  );
}

// ── Shared micro-components ───────────────────────────────────────────────────

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: "green" | "red" | "yellow";
}) {
  const color = highlight
    ? `var(--${highlight})`
    : "var(--text)";
  return (
    <div
      className="rounded-lg px-3 py-2"
      style={{ background: "var(--bg)", border: "1px solid var(--border)" }}
    >
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="font-semibold text-sm" style={{ color }}>
        {value}
      </div>
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

function fmt(n?: number | null) {
  return n != null ? n.toFixed(2) : "—";
}

function fmtTs(ts: string) {
  return new Date(ts).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
