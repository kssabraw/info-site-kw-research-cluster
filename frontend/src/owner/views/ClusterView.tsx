import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getAllSurvivingKeywords,
  getClusters,
  type Cluster,
  type CoverageGap,
  type Keyword,
} from "../../shared/api";
import { useSession } from "../SessionWorkspace";

// Cluster View (PRD §9.2): article units grouped by parent topic. One cluster =
// one planned article. Coverage gaps appear inline as flagged placeholder rows.
// Editing (rename, move, merge, split, accept gap, …) is M7b — read-only here.
export function ClusterView() {
  const { sessionId, topics } = useSession();
  const clustersQ = useQuery({ queryKey: ["clusters", sessionId], queryFn: () => getClusters(sessionId) });
  const keywordsQ = useQuery({ queryKey: ["keywords-all", sessionId], queryFn: () => getAllSurvivingKeywords(sessionId) });

  const byCluster = useMemo(() => {
    const m = new Map<string, Keyword[]>();
    keywordsQ.data?.forEach((k) => {
      if (!k.cluster_id) return;
      const arr = m.get(k.cluster_id) ?? [];
      arr.push(k);
      m.set(k.cluster_id, arr);
    });
    return m;
  }, [keywordsQ.data]);

  const clusterName = useMemo(() => {
    const m = new Map<string, string>();
    clustersQ.data?.clusters.forEach((c) => m.set(c.id, c.name));
    return (id: string) => m.get(id) ?? "—";
  }, [clustersQ.data]);

  if (clustersQ.isLoading || keywordsQ.isLoading) return <p className="muted">Loading article plan…</p>;
  if (clustersQ.isError) return <p className="form-error">Failed to load article plan.</p>;

  const clusters = clustersQ.data?.clusters ?? [];
  const gaps = clustersQ.data?.coverage_gaps ?? [];
  if (clusters.length === 0)
    return <p className="muted">No article plan yet. Run article planning for this session.</p>;

  // Only topics that actually have articles or gaps, in the session's topic order.
  const topicsWithContent = topics.filter(
    (t) => clusters.some((c) => c.topic_id === t.id) || gaps.some((g) => g.topic_id === t.id),
  );

  return (
    <div className="cluster-tree">
      {topicsWithContent.map((t) => (
        <TopicGroup
          key={t.id}
          name={t.name}
          relationship={t.relationship_type}
          clusters={clusters.filter((c) => c.topic_id === t.id)}
          gaps={gaps.filter((g) => g.topic_id === t.id)}
          byCluster={byCluster}
          clusterName={clusterName}
        />
      ))}
    </div>
  );
}

function TopicGroup({
  name,
  relationship,
  clusters,
  gaps,
  byCluster,
  clusterName,
}: {
  name: string;
  relationship: string;
  clusters: Cluster[];
  gaps: CoverageGap[];
  byCluster: Map<string, Keyword[]>;
  clusterName: (id: string) => string;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="topic-group">
      <button className="topic-group-head" onClick={() => setOpen((o) => !o)}>
        <span className="tree-caret">{open ? "▼" : "▶"}</span>
        <span className="topic-group-name">{name}</span>
        <span className="badge">{relationship}</span>
        <span className="topic-group-count">{clusters.length} articles</span>
      </button>
      {open && (
        <div className="topic-group-body">
          {clusters.map((c) => (
            <ArticleRow key={c.id} cluster={c} keywords={byCluster.get(c.id) ?? []} clusterName={clusterName} />
          ))}
          {gaps.filter((g) => g.status !== "dismissed").map((g) => (
            <div key={g.id} className="gap-row">
              <span className="gap-mark">⚠ Gap</span>
              <span>{g.suggested_title}</span>
              {g.rationale && <span className="cell-muted">— {g.rationale}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ArticleRow({
  cluster,
  keywords,
  clusterName,
}: {
  cluster: Cluster;
  keywords: Keyword[];
  clusterName: (id: string) => string;
}) {
  const [open, setOpen] = useState(false);
  const primary = keywords.find((k) => k.is_primary_for_cluster) ?? keywords.find((k) => k.id === cluster.primary_keyword_id);
  const supporting = keywords.filter((k) => k.id !== primary?.id);
  const links = cluster.peer_article_links ?? [];

  return (
    <div className="article-row">
      <button className="article-head" onClick={() => setOpen((o) => !o)}>
        <span className="tree-caret">{open ? "▼" : "▶"}</span>
        <span className="article-name">{cluster.name}</span>
        {cluster.intent && <span className="badge badge-rel">{cluster.intent}</span>}
        {cluster.is_gap_placeholder && <span className="badge badge-warn">gap placeholder</span>}
        <span className="topic-group-count">{keywords.length} kw</span>
      </button>
      {open && (
        <div className="article-detail">
          <DetailLine label="Primary">{primary?.keyword ?? <span className="cell-muted">—</span>}</DetailLine>
          <DetailLine label="Supporting">
            {supporting.length ? supporting.map((k) => k.keyword).join(", ") : <span className="cell-muted">none</span>}
          </DetailLine>
          {cluster.suggested_h2s && cluster.suggested_h2s.length > 0 && (
            <DetailLine label="H2 outline">{cluster.suggested_h2s.join(" · ")}</DetailLine>
          )}
          {links.length > 0 && <DetailLine label="Links to">{links.map(clusterName).join(", ")}</DetailLine>}
          {cluster.orchestrator_notes && (
            <DetailLine label="Notes"><span className="cell-muted">{cluster.orchestrator_notes}</span></DetailLine>
          )}
        </div>
      )}
    </div>
  );
}

function DetailLine({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="detail-line">
      <span className="detail-label">{label}</span>
      <span className="detail-value">{children}</span>
    </div>
  );
}
