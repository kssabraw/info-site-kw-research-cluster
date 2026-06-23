import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { downloadAllArticles, listArticles, type ArticleListItem } from "../../shared/api";
import ArticlePanel from "./ArticlePanel";
import { useSession } from "../SessionWorkspace";

// M15 follow-on — Articles library (owner). Lists every written article for a session
// (latest per cluster: words, cost, date, scheduled-or-ad-hoc); click to read the full
// Markdown and Copy / Download .md. Articles live in fanout.article_outputs (Supabase) as
// the source of truth; this is the browse + read + export-one surface.
export function ArticlesView() {
  const { sessionId } = useSession();
  const [openCluster, setOpenCluster] = useState<{ id: string; name: string } | null>(null);

  const q = useQuery({
    queryKey: ["articles", sessionId],
    queryFn: () => listArticles(sessionId),
    refetchInterval: 20000,
  });
  const downloadAll = useMutation({
    mutationFn: () => downloadAllArticles(sessionId),
    onSuccess: (res) => window.open(res.download_url, "_blank", "noopener"),
    onError: (e: Error) => alert(e.message),
  });

  if (q.isLoading) return <p className="muted">Loading articles…</p>;
  if (q.isError) return <p className="form-error">Couldn’t load articles.</p>;

  const articles = q.data?.articles ?? [];

  return (
    <div>
      <div className="edit-toolbar">
        <button
          className="btn btn-ghost"
          style={{ width: "auto" }}
          disabled={articles.length === 0 || downloadAll.isPending}
          title="Download every written article as a .zip of Markdown files"
          onClick={() => downloadAll.mutate()}
        >
          {downloadAll.isPending ? "Zipping…" : "Download all (.zip)"}
        </button>
        <span className="muted">
          {articles.length} written article{articles.length === 1 ? "" : "s"} · stored in the app.
          Generate or schedule articles from the Cluster tab; they appear here when done.
        </span>
      </div>

      {articles.length === 0 ? (
        <p className="muted">No articles written yet for this session.</p>
      ) : (
        <table className="kw-table">
          <thead>
            <tr><th>Article</th><th>Words</th><th>Cost</th><th>Source</th><th>Written</th><th></th></tr>
          </thead>
          <tbody>
            {articles.map((a: ArticleListItem) => (
              <tr key={a.cluster_id}>
                <td>{a.name}</td>
                <td>{a.total_word_count ?? "—"}</td>
                <td>{a.cost_usd != null ? `$${Number(a.cost_usd).toFixed(2)}` : "—"}</td>
                <td>
                  <span className="badge">{a.scheduled ? "scheduled" : "ad-hoc"}</span>
                </td>
                <td className="cell-muted">
                  {a.generated_at ? new Date(a.generated_at).toLocaleString() : "—"}
                </td>
                <td>
                  <button className="link-btn" onClick={() => setOpenCluster({ id: a.cluster_id, name: a.name })}>
                    Read
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {openCluster && (
        <ArticlePanel
          sessionId={sessionId}
          clusterId={openCluster.id}
          keyword={openCluster.name}
          readOnly
          onClose={() => setOpenCluster(null)}
        />
      )}
    </div>
  );
}
