import { useQuery } from "@tanstack/react-query";
import { getMe, getProjects } from "../shared/api";
import { useAuth } from "../shared/auth";

export function ProjectList() {
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
        <h1 className="page-title">Projects</h1>

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
