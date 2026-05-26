import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getMe } from "./api";
import { useAuth } from "./auth";

// Shared top bar + page frame for every Owner view. The brand links home; the
// right side shows the signed-in user and a sign-out control.
export function AppShell({ children }: { children: ReactNode }) {
  const { signOut } = useAuth();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });

  return (
    <>
      <header className="topbar">
        <Link to="/projects" className="brand" style={{ textDecoration: "none", color: "inherit" }}>
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Topic Fanout</span>
        </Link>
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
      {children}
    </>
  );
}
