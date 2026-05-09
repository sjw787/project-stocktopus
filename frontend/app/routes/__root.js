import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { createRootRoute, Link, Outlet, ScrollRestoration, } from "@tanstack/react-router";
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
    return (_jsxs(QueryClientProvider, { client: queryClient, children: [_jsxs("div", { className: "min-h-screen flex flex-col", children: [_jsx(Nav, {}), _jsx("main", { className: "flex-1 px-4 py-6 max-w-7xl mx-auto w-full", children: _jsx(Outlet, {}) })] }), _jsx(ScrollRestoration, {}), _jsx(TanStackRouterDevtools, { position: "bottom-right" })] }));
}
function Nav() {
    return (_jsxs("nav", { style: {
            borderBottom: "1px solid var(--border)",
            background: "var(--bg-card)",
        }, className: "px-4 py-3 flex items-center gap-6", children: [_jsx("span", { className: "font-bold text-lg", style: { color: "var(--accent)" }, children: "\uD83D\uDC19 Stocktopus" }), _jsx(NavLink, { to: "/", children: "Dashboard" }), _jsx(NavLink, { to: "/strategy", children: "Strategy" }), _jsx(NavLink, { to: "/paper", children: "Paper" }), _jsx(NavLink, { to: "/news", children: "News" })] }));
}
function NavLink({ to, children, }) {
    return (_jsx(Link, { to: to, className: "text-sm transition-colors", style: { color: "var(--text-muted)" }, activeProps: { style: { color: "var(--text)" } }, children: children }));
}
