import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle, RefreshCw, Zap, ZapOff } from "lucide-react";
import { api, type PaperDrift, type PaperStatus, type PaperTrade } from "~/lib/api";

export const Route = createFileRoute("/paper")({
  component: PaperPage,
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

// ── Status card ───────────────────────────────────────────────────────────────

function StatusCard() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery<PaperStatus>({
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

  return (
    <Card title="Paper Trading Status">
      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <EmptyState message="Backend unreachable" />
      ) : (
        <div className="space-y-4">
          {/* Gate progress */}
          <div>
            <div className="flex justify-between text-xs mb-1" style={{ color: "var(--text-muted)" }}>
              <span>Phase 8 gate</span>
              <span>{data.trades_completed}/100 trades · {data.regimes_seen}/3 regimes</span>
            </div>
            <div className="rounded-full h-2 overflow-hidden" style={{ background: "var(--border)" }}>
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(100, data.trades_completed)}%`,
                  background: data.phase8_gate ? "var(--green)" : "var(--accent)",
                }}
              />
            </div>
            {data.phase8_gate && (
              <div className="flex items-center gap-1 mt-1 text-xs" style={{ color: "var(--green)" }}>
                <CheckCircle size={12} />
                Gate cleared — ready for Phase 9
              </div>
            )}
          </div>

          {/* P&L stats */}
          <div className="grid grid-cols-2 gap-2">
            <StatTile label="Today P&L" value={`$${data.daily_pnl.toFixed(2)}`} color={data.daily_pnl >= 0 ? "var(--green)" : "var(--red)"} />
            <StatTile label="Total P&L" value={`$${data.total_pnl.toFixed(2)}`} color={data.total_pnl >= 0 ? "var(--green)" : "var(--red)"} />
            <StatTile label="Open Positions" value={String(data.open_positions)} />
            <StatTile label="Kill Switch" value={data.kill_switch_active ? "ACTIVE" : "off"} color={data.kill_switch_active ? "var(--red)" : undefined} />
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <button
              onClick={() => tick.mutate()}
              disabled={tick.isPending || data.kill_switch_active}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80 disabled:opacity-40"
              style={{ background: "var(--accent)", color: "#fff" }}
            >
              {tick.isPending ? <RefreshCw size={13} className="animate-spin" /> : <Zap size={13} />}
              Tick
            </button>
            <button
              onClick={() => kill.mutate()}
              disabled={kill.isPending}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80 disabled:opacity-40"
              style={{ background: "var(--red)", color: "#fff" }}
            >
              {kill.isPending ? <RefreshCw size={13} className="animate-spin" /> : <ZapOff size={13} />}
              Kill All
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Drift alarm card ──────────────────────────────────────────────────────────

function DriftCard() {
  const { data, isLoading, isError } = useQuery<PaperDrift>({
    queryKey: ["paper-drift"],
    queryFn: api.paperDrift,
    refetchInterval: 60_000,
  });

  return (
    <Card title="Drift Alarm">
      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <EmptyState message="No drift data available" />
      ) : (
        <div className="space-y-3">
          {/* Alarm status */}
          <div className="flex items-center gap-2">
            {data.alarm_active ? (
              <>
                <AlertTriangle size={16} style={{ color: "var(--red)" }} />
                <span className="text-sm font-semibold" style={{ color: "var(--red)" }}>
                  ALARM ACTIVE
                </span>
              </>
            ) : (
              <>
                <CheckCircle size={16} style={{ color: "var(--green)" }} />
                <span className="text-sm font-semibold" style={{ color: "var(--green)" }}>
                  Distribution healthy
                </span>
              </>
            )}
          </div>

          {data.alarm_reasons.length > 0 && (
            <ul className="space-y-1">
              {data.alarm_reasons.map((r, i) => (
                <li key={i} className="text-xs" style={{ color: "var(--red)" }}>
                  · {r}
                </li>
              ))}
            </ul>
          )}

          {/* Metrics */}
          <div className="grid grid-cols-2 gap-2">
            <StatTile label="Trades sampled" value={String(data.n_trades)} />
            <StatTile label="Win rate" value={`${(data.win_rate * 100).toFixed(1)}%`} />
            <StatTile label="Profit factor" value={data.profit_factor?.toFixed(2) ?? "∞"} />
            <StatTile label="Expectancy" value={`$${data.expectancy.toFixed(2)}`} />
          </div>

          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Regimes: {data.regimes_seen.join(", ") || "—"}
          </div>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Checked {new Date(data.checked_at).toLocaleString()}
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Trade journal ─────────────────────────────────────────────────────────────

function TradeJournal() {
  const { data, isLoading, isError } = useQuery<PaperTrade[]>({
    queryKey: ["paper-trades"],
    queryFn: () => api.paperTrades(),
    refetchInterval: 30_000,
  });

  return (
    <Card title="Trade Journal" className="col-span-full">
      {isLoading ? (
        <Spinner />
      ) : isError || !data?.length ? (
        <EmptyState message="No paper trades yet — run a tick to start" />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                <th className="text-left py-1 pr-3">Entry</th>
                <th className="text-left py-1 pr-3">Symbol</th>
                <th className="text-left py-1 pr-3">Dir</th>
                <th className="text-right py-1 pr-3">Qty</th>
                <th className="text-right py-1 pr-3">Entry $</th>
                <th className="text-right py-1 pr-3">Exit $</th>
                <th className="text-right py-1 pr-3">P&L</th>
                <th className="text-left py-1 pr-3">Regime</th>
                <th className="text-left py-1">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((t) => (
                <tr
                  key={t.id}
                  style={{ borderBottom: "1px solid var(--border)" }}
                  className="hover:opacity-80 transition-opacity"
                >
                  <td className="py-1 pr-3" style={{ color: "var(--text-muted)" }}>
                    {new Date(t.entry_ts).toLocaleDateString()}
                  </td>
                  <td className="py-1 pr-3 font-semibold">{t.symbol}</td>
                  <td
                    className="py-1 pr-3 font-semibold"
                    style={{ color: t.direction === "long" ? "var(--green)" : "var(--red)" }}
                  >
                    {t.direction.toUpperCase()}
                  </td>
                  <td className="text-right py-1 pr-3">{t.qty}</td>
                  <td className="text-right py-1 pr-3">{t.entry_price.toFixed(2)}</td>
                  <td className="text-right py-1 pr-3">{t.exit_price?.toFixed(2) ?? "—"}</td>
                  <td
                    className="text-right py-1 pr-3 font-semibold"
                    style={{ color: (t.realized_pnl ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}
                  >
                    {t.realized_pnl != null ? `$${t.realized_pnl.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-1 pr-3" style={{ color: "var(--text-muted)" }}>
                    {t.regime ?? "—"}
                  </td>
                  <td className="py-1">
                    <span
                      className="rounded-full px-2 py-0.5 text-xs"
                      style={{
                        background: t.status === "open" ? "var(--accent)" : "var(--border)",
                        color: t.status === "open" ? "#fff" : "var(--text-muted)",
                      }}
                    >
                      {t.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ── Stat tile ─────────────────────────────────────────────────────────────────

function StatTile({ label, value, color }: { label: string; value: string; color?: string }) {
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

function PaperPage() {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <Zap size={18} style={{ color: "var(--accent)" }} />
        <h1 className="text-lg font-semibold">Paper Trading</h1>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <StatusCard />
        <DriftCard />
      </div>

      <div className="grid grid-cols-1 gap-4">
        <TradeJournal />
      </div>
    </div>
  );
}
