import {
  createRootRoute,
  Link,
  Outlet,
  ScrollRestoration,
} from "@tanstack/react-router";
import { TanStackRouterDevtools } from "@tanstack/router-devtools";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

export const Route = createRootRoute({
  component: RootComponent,
});

function RootComponent() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen flex flex-col">
        <Nav />
        <main className="flex-1 px-4 py-6 max-w-7xl mx-auto w-full">
          <Outlet />
        </main>
      </div>
      <ScrollRestoration />
      <TanStackRouterDevtools position="bottom-right" />
    </QueryClientProvider>
  );
}

function Nav() {
  return (
    <nav
      style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-card)",
      }}
      className="px-4 py-3 flex items-center gap-6"
    >
      <span className="font-bold text-lg" style={{ color: "var(--accent)" }}>
        🐙 Stocktopus
      </span>
      <NavLink to="/">Dashboard</NavLink>
      <NavLink to="/news">News</NavLink>
    </nav>
  );
}

function NavLink({
  to,
  children,
}: {
  to: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      to={to}
      className="text-sm transition-colors"
      style={{ color: "var(--text-muted)" }}
      activeProps={{ style: { color: "var(--text)" } }}
    >
      {children}
    </Link>
  );
}
