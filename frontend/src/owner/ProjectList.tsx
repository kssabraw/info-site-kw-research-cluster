import { useQuery } from "@tanstack/react-query";
import { getMe, getProjects } from "../shared/api";
import { useAuth } from "../shared/auth";

export function ProjectList() {
  const { signOut } = useAuth();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const projects = useQuery({ queryKey: ["projects"], queryFn: getProjects });

  return (
    <main style={{ maxWidth: 640, margin: "5vh auto", fontFamily: "system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Projects</h1>
        <button onClick={() => signOut()}>Sign out</button>
      </header>

      {me.data && (
        <p style={{ color: "#555" }}>
          Signed in as {me.data.email} ({me.data.role})
        </p>
      )}

      {projects.isLoading && <p>Loading projects…</p>}
      {projects.isError && <p style={{ color: "crimson" }}>Failed to load projects.</p>}

      {projects.data && (
        <ul>
          {projects.data.map((p) => (
            <li key={p.id}>
              {p.name}
              {p.is_scratch ? " (Scratch)" : ""}
            </li>
          ))}
        </ul>
      )}
      {projects.data && projects.data.length === 0 && <p>No projects yet.</p>}
    </main>
  );
}
