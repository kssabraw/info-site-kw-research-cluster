import { useAuth } from "./shared/auth";
import { Login } from "./shared/Login";
import { ProjectList } from "./owner/ProjectList";

// M1 renders a single project-list view for any signed-in user. The Owner
// three-view UI (§9) and the VA wizard (§10) arrive in M7 / M8.
export default function App() {
  const { session, loading } = useAuth();

  if (loading) {
    return <div className="state-center">Loading…</div>;
  }

  return session ? <ProjectList /> : <Login />;
}
