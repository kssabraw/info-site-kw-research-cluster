import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getProjects, listSessions, type SessionListItem } from "../shared/api";
import { AppShell } from "../shared/AppShell";
import { statusLabel, statusClass } from "../shared/sessionStatus";

// Project + Session Browser (PRD §9.4). Left rail lists projects; the main pane
// lists the selected project's sessions and resumes any of them. Per-session
// mutations (move / duplicate / archive / delete) land in M7b.
export function ProjectsPage() {
  const navigate = useNavigate();
  const projects = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const [selected, setSelected] = useState<string | null>(null);

  // Default to the first project (Scratch sorts first) once they load.
  useEffect(() => {
    if (!selected && projects.data && projects.data.length > 0) {
      setSelected(projects.data[0].id);
    }
  }, [projects.data, selected]);

  const sessions = useQuery({
    queryKey: ["sessions", selected],
    queryFn: () => listSessions(selected!),
    enabled: !!selected,
  });

  const selectedProject = projects.data?.find((p) => p.id === selected);

  return (
    <AppShell>
      <div className="browser-layout">
        <aside className="browser-rail">
          <div className="browser-rail-head">Projects</div>
          {projects.isLoading && <p className="muted" style={{ padding: "0 14px" }}>Loading…</p>}
          {projects.data?.map((p) => (
            <button
              key={p.id}
              className={"rail-item" + (p.id === selected ? " rail-item-active" : "")}
              onClick={() => setSelected(p.id)}
            >
              <span className="rail-item-name">{p.name}</span>
              {p.is_scratch && <span className="tag-scratch">Scratch</span>}
            </button>
          ))}
        </aside>

        <main className="browser-main">
          <div className="silo-head" style={{ marginBottom: 20 }}>
            <h1 className="page-title" style={{ margin: 0 }}>
              {selectedProject?.name ?? "Sessions"}
            </h1>
            <button
              className="btn btn-primary"
              style={{ width: "auto" }}
              onClick={() => navigate("/session/new")}
            >
              New research session
            </button>
          </div>

          {sessions.isLoading && (
            <div className="project-grid">
              <div className="skeleton" />
              <div className="skeleton" />
            </div>
          )}
          {sessions.isError && (
            <p className="form-error">Failed to load sessions. Please try again.</p>
          )}
          {sessions.data && sessions.data.length === 0 && (
            <p className="muted">No sessions in this project yet.</p>
          )}
          {sessions.data && sessions.data.length > 0 && (
            <div className="session-list">
              {sessions.data.map((s) => (
                <SessionRow key={s.id} session={s} onOpen={() => navigate(`/session/${s.id}`)} />
              ))}
            </div>
          )}
        </main>
      </div>
    </AppShell>
  );
}

function SessionRow({
  session,
  onOpen,
}: {
  session: SessionListItem;
  onOpen: () => void;
}) {
  return (
    <button className="session-row" onClick={onOpen}>
      <div className="session-row-main">
        <span className="session-row-seed">{session.seed_keyword}</span>
        <span className={"status-pill " + statusClass(session.status)}>
          {statusLabel(session.status)}
        </span>
      </div>
      <div className="session-row-meta">
        <span>{session.coverage_mode}</span>
        <span>·</span>
        <span>{session.cluster_count} articles</span>
        <span>·</span>
        <span>{new Date(session.created_at).toLocaleDateString()}</span>
      </div>
    </button>
  );
}
