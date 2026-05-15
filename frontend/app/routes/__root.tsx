import {
  createRootRoute,
  Link,
  Outlet,
  ScrollRestoration,
} from "@tanstack/react-router";
import { TanStackRouterDevtools } from "@tanstack/router-devtools";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import "../styles.css";
import { isAuthenticated, signOut } from "~/lib/auth";
import { LoginPage } from "~/components/LoginPage";

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
      <AuthGate />
    </QueryClientProvider>
  );
}

function AuthGate() {
  const [authed, setAuthed] = useState<boolean | null>(null); // null = loading

  useEffect(() => {
    isAuthenticated().then(setAuthed);
  }, []);

  if (authed === null) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)" }}>
        <span style={{ color: "var(--text-muted)" }}>Loading…</span>
      </div>
    );
  }

  if (!authed) {
    return <LoginPage onSuccess={() => setAuthed(true)} />;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Nav onSignOut={() => setAuthed(false)} />
      <main className="flex-1 px-4 py-6 max-w-7xl mx-auto w-full">
        <Outlet />
      </main>
      <ScrollRestoration />
      <TanStackRouterDevtools position="bottom-right" />
    </div>
  );
}

function Nav({ onSignOut }: { onSignOut: () => void }) {
  async function handleSignOut() {
    await signOut();
    queryClient.clear();
    onSignOut();
  }

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
      <NavLink to="/strategy">Strategy</NavLink>
      <NavLink to="/paper">Paper</NavLink>
      <NavLink to="/news">News</NavLink>
      <button
        onClick={() => void handleSignOut()}
        className="ml-auto text-sm transition-opacity hover:opacity-70"
        style={{ color: "var(--text-muted)" }}
      >
        Sign out
      </button>
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
