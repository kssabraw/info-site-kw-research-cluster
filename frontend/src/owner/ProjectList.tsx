import { useQuery } from "@tanstack/react-query";
import { getMe, getProjects } from "../shared/api";
import { useAuth } from "../shared/auth";

export function ProjectList({ onNewSession }: { onNewSession: () => void }) {
  const { signOut } = useAuth();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const projects = useQuery({ queryKey: ["projects"], queryFn: getProjects });

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Topic Fanout</span>
        </div>
        <div className="topbar-user">
          {me.data && (
            <>
              <span>{me.data.email}</span>
              <span className="role-badge">{me.data.role}</span>
            </>
          )}
          <button className="btn btn-ghost" onClick={() => signOut()}>
            Sign out
          </button>
        </div>
      </header>

      <main className="content">
        <div className="silo-head" style={{ marginBottom: 20 }}>
          <h1 className="page-title" style={{ margin: 0 }}>
            Projects
          </h1>
          <button className="btn btn-primary" style={{ width: "auto" }} onClick={onNewSession}>
            New research session
          </button>
        </div>

        {projects.isLoading && (
          <div className="project-grid">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}

        {projects.isError && (
          <p className="form-error">Failed to load projects. Please try again.</p>
        )}

        {projects.data && projects.data.length > 0 && (
          <div className="project-grid">
            {projects.data.map((p) => (
              <div className="project-card" key={p.id}>
                <p className="project-card-name">
                  {p.name}
                  {p.is_scratch && <span className="tag-scratch">Scratch</span>}
                </p>
                <span className="project-card-meta">
                  Created {new Date(p.created_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        )}

        {projects.data && projects.data.length === 0 && (
          <p className="muted">No projects yet.</p>
        )}
      </main>
    </>
  );
}
