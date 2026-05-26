import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getMe, getSession, getSummary, type Silo } from "../shared/api";
import { AppShell } from "../shared/AppShell";
import { hasResults, statusClass, statusLabel } from "../shared/sessionStatus";

export interface SessionCtx {
  sessionId: string;
  topics: Silo[];
  topicName: (id: string) => string;
  // Drives the restricted VA editing surface in the shared views (PRD §10).
  role: "owner" | "va";
}

export function useSession() {
  return useOutletContext<SessionCtx>();
}

// VAs get a simplified two-view results surface + read-only architecture; no
// split view (PRD §10.2 / §10.3).
const OWNER_TABS = [
  { to: "table", label: "Table" },
  { to: "cluster", label: "Cluster" },
  { to: "architecture", label: "Architecture" },
  { to: "split", label: "Split" },
];
const VA_TABS = [
  { to: "table", label: "Table" },
  { to: "cluster", label: "Cluster" },
  { to: "architecture", label: "Architecture" },
];

// Per-session shell (PRD §9): segmented control over the three views, fed by the
// read-only M1–M6 API. Views render against the shared topic map below.
export function SessionWorkspace() {
  const { id } = useParams<{ id: string }>();
  const sessionId = id!;

  const session = useQuery({ queryKey: ["session", sessionId], queryFn: () => getSession(sessionId) });
  const summary = useQuery({
    queryKey: ["summary", sessionId],
    queryFn: () => getSummary(sessionId),
    refetchInterval: (q) => (q.state.data?.status === "running" ? 4000 : false),
  });
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const role: "owner" | "va" = me.data?.role === "owner" ? "owner" : "va";

  const status = summary.data?.status ?? session.data?.status;
  const topics = session.data?.silos ?? [];
  const topicName = (tid: string) => topics.find((t) => t.id === tid)?.name ?? "Unknown topic";
  const tabs = role === "owner" ? OWNER_TABS : VA_TABS;

  return (
    <AppShell>
      <div className="workspace-head">
        <div className="workspace-head-row">
          <h1 className="page-title" style={{ margin: 0 }}>
            {session.data?.seed_keyword ?? "Session"}
          </h1>
          {status && (
            <span className={"status-pill " + statusClass(status)}>{statusLabel(status)}</span>
          )}
        </div>
        <nav className="segmented">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) => "segmented-item" + (isActive ? " segmented-item-active" : "")}
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <main className="content content-wide">
        {(session.isLoading || summary.isLoading) && <p className="muted">Loading session…</p>}
        {session.isError && <p className="form-error">Couldn’t load this session.</p>}

        {status === "running" && (
          <div className="card" style={{ textAlign: "center" }}>
            <div className="spinner" />
            <p className="muted">This session is still running. Results will appear when it finishes.</p>
          </div>
        )}

        {status && status !== "running" && !hasResults(status) && (
          <div className="card">
            <p style={{ margin: 0, fontWeight: 600 }}>This session hasn’t produced results yet.</p>
            <p className="muted" style={{ marginBottom: 0 }}>
              It’s at the “{statusLabel(status)}” stage. Resuming an in-progress run from the UI
              arrives later; for now, open it from the creation flow or run the remaining pipeline
              steps via the API.
            </p>
          </div>
        )}

        {status && hasResults(status) && session.data && (
          <Outlet context={{ sessionId, topics, topicName, role } satisfies SessionCtx} />
        )}
      </main>
    </AppShell>
  );
}
