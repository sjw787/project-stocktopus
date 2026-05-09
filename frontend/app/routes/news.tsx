import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Newspaper, RefreshCw, AlertTriangle, ExternalLink } from "lucide-react";
import { api, type NewsItem } from "~/lib/api";

export const Route = createFileRoute("/news")({
  component: NewsPage,
});

function NewsPage() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["news"],
    queryFn: () => api.news(40),
    refetchInterval: 120_000,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Newspaper size={18} style={{ color: "var(--accent)" }} />
          <h1 className="text-lg font-semibold">News Feed</h1>
        </div>
        <button
          onClick={() => void refetch()}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg transition-opacity hover:opacity-70"
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            color: "var(--text-muted)",
          }}
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <LoadingRows />
      ) : isError ? (
        <ErrorState />
      ) : !data?.length ? (
        <EmptyState />
      ) : (
        <NewsList items={data} />
      )}
    </div>
  );
}

function NewsList({ items }: { items: NewsItem[] }) {
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <NewsCard key={item.id} item={item} />
      ))}
    </div>
  );
}

function NewsCard({ item }: { item: NewsItem }) {
  const score = item.sentiment_score;
  const sentimentColor =
    score == null
      ? "var(--text-muted)"
      : score > 0.1
        ? "var(--green)"
        : score < -0.1
          ? "var(--red)"
          : "var(--yellow)";

  return (
    <div
      className="rounded-xl p-4 hover:opacity-90 transition-opacity"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium hover:underline flex items-start gap-1"
          >
            {item.headline}
            <ExternalLink size={10} className="mt-1 flex-shrink-0" style={{ color: "var(--text-muted)" }} />
          </a>
          {item.summary && (
            <p className="text-xs mt-1 line-clamp-2" style={{ color: "var(--text-muted)" }}>
              {item.summary}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              {item.source}
            </span>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              {fmtDate(item.published_at)}
            </span>
            {item.symbols.length > 0 && (
              <div className="flex gap-1">
                {item.symbols.slice(0, 3).map((s) => (
                  <span
                    key={s}
                    className="text-xs px-1.5 py-0.5 rounded"
                    style={{
                      background: "var(--accent-dim)",
                      color: "var(--text)",
                      opacity: 0.8,
                    }}
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}
            {item.categories.length > 0 && (
              <div className="flex gap-1">
                {item.categories.map((c) => (
                  <span
                    key={c}
                    className="text-xs px-1.5 py-0.5 rounded"
                    style={{
                      background: "var(--bg)",
                      border: "1px solid var(--border)",
                      color: "var(--text-muted)",
                    }}
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
        {score != null && (
          <div className="flex-shrink-0 text-right">
            <div
              className="text-xs font-semibold"
              style={{ color: sentimentColor }}
            >
              {score > 0 ? "+" : ""}
              {score.toFixed(2)}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              sentiment
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-20 rounded-xl animate-pulse"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
        />
      ))}
    </div>
  );
}

function ErrorState() {
  return (
    <div
      className="rounded-xl p-6 flex items-center gap-2"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        color: "var(--red)",
      }}
    >
      <AlertTriangle size={16} />
      <span className="text-sm">Failed to load news — is the backend running?</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div
      className="rounded-xl p-6 flex items-center gap-2"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        color: "var(--text-muted)",
      }}
    >
      <Newspaper size={16} />
      <span className="text-sm">No news yet — run the news ingestion job first.</span>
    </div>
  );
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
