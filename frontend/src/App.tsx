import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./shared/auth";
import { Login } from "./shared/Login";
import { ProjectsPage } from "./owner/ProjectsPage";
import { NewSession } from "./owner/NewSession";
import { SessionWorkspace } from "./owner/SessionWorkspace";
import { TableView } from "./owner/views/TableView";
import { ClusterView } from "./owner/views/ClusterView";
import { ArchitectureView } from "./owner/views/ArchitectureView";
import { SplitView } from "./owner/views/SplitView";

// M7 (Owner UI): URL-addressable views so a session is deep-linkable and
// resumable (PRD §9.4). The VA wizard (§10) is M8.
export default function App() {
  const { session, loading } = useAuth();

  if (loading) {
    return <div className="state-center">Loading…</div>;
  }
  if (!session) {
    return <Login />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/projects" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/session/new" element={<NewSession />} />
        <Route path="/session/:id" element={<SessionWorkspace />}>
          <Route index element={<Navigate to="table" replace />} />
          <Route path="table" element={<TableView />} />
          <Route path="cluster" element={<ClusterView />} />
          <Route path="architecture" element={<ArchitectureView />} />
          <Route path="split" element={<SplitView />} />
        </Route>
        <Route path="*" element={<Navigate to="/projects" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
