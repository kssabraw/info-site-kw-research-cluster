import { useState } from "react";
import { useAuth } from "./shared/auth";
import { Login } from "./shared/Login";
import { ProjectList } from "./owner/ProjectList";
import { SiloDiscovery } from "./owner/SiloDiscovery";

type View = "projects" | "discovery";

// M1 added login + project list. M2 adds the silo-discovery flow reachable from
// the dashboard. The Owner three-view UI (§9) and VA wizard (§10) arrive later.
export default function App() {
  const { session, loading } = useAuth();
  const [view, setView] = useState<View>("projects");

  if (loading) {
    return <div className="state-center">Loading…</div>;
  }
  if (!session) {
    return <Login />;
  }

  if (view === "discovery") {
    return <SiloDiscovery onExit={() => setView("projects")} />;
  }
  return <ProjectList onNewSession={() => setView("discovery")} />;
}
