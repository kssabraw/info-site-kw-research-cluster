import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptGap,
  bulkKeywordMove,
  deleteCluster,
  dismissGap,
  editCluster,
  getAllSurvivingKeywords,
  getClusters,
  mergeClusters,
  planArticles,
  promotePrimary,
  splitCluster,
  type Cluster,
  type CoverageGap,
  type Keyword,
} from "../../shared/api";
import { useSession } from "../SessionWorkspace";

const INTENTS = ["informational", "commercial", "transactional", "comparison", "navigational"];

// Cluster View (PRD §9.2): article units grouped by parent topic, fully editable.
// All edits write straight to Postgres and the orchestrator never re-runs on its
// own (§9.2). "Re-run orchestrator" is an explicit, destructive action.
export function ClusterView() {
  const { sessionId, topics, role } = useSession();
  const isVA = role === "va";
  const qc = useQueryClient();
  const clustersQ = useQuery({ queryKey: ["clusters", sessionId], queryFn: () => getClusters(sessionId) });
  const keywordsQ = useQuery({ queryKey: ["keywords-all", sessionId], queryFn: () => getAllSurvivingKeywords(sessionId) });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["clusters", sessionId] });
    qc.invalidateQueries({ queryKey: ["keywords-all", sessionId] });
    // Structural edits (delete/merge/split/accept-gap) clear the stored
    // architecture server-side, so drop its cached copy too.
    qc.invalidateQueries({ queryKey: ["architecture", sessionId] });
  };
  const edit = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: invalidate,
    onError: (e: Error) => alert(e.message),
  });
  const run = (fn: () => Promise<unknown>) => edit.mutate(fn);

  const rerun = useMutation({
    mutationFn: () => planArticles(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["summary", sessionId] }),
    onError: (e: Error) => alert(e.message),
  });

  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSel, setMergeSel] = useState<Set<string>>(new Set());

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

  const topicsWithContent = topics.filter(
    (t) => clusters.some((c) => c.topic_id === t.id) || gaps.some((g) => g.topic_id === t.id),
  );

  function toggleMerge(id: string) {
    const next = new Set(mergeSel);
    next.has(id) ? next.delete(id) : next.add(id);
    setMergeSel(next);
  }
  function doMerge() {
    const ids = [...mergeSel];
    if (ids.length < 2) return;
    const survivor = clusters.find((c) => c.id === ids[0]);
    const name = window.prompt("Merged article name:", survivor?.name ?? "");
    if (name === null) return;
    run(() => mergeClusters(ids[0], ids, name || undefined));
    setMergeMode(false);
    setMergeSel(new Set());
  }

  return (
    <div>
      {isVA ? (
        <div className="edit-toolbar">
          <span className="muted">
            You can rename articles and move keywords between them. Restructuring
            (split, merge, delete) is handled by your workspace owner.
          </span>
        </div>
      ) : (
      <div className="edit-toolbar">
        {mergeMode ? (
          <>
            <span className="muted">{mergeSel.size} selected (first = survivor)</span>
            <button className="btn btn-primary" style={{ width: "auto" }} disabled={mergeSel.size < 2} onClick={doMerge}>
              Merge {mergeSel.size} articles
            </button>
            <button className="btn btn-ghost" style={{ width: "auto" }} onClick={() => { setMergeMode(false); setMergeSel(new Set()); }}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button className="btn btn-ghost" style={{ width: "auto" }} onClick={() => setMergeMode(true)}>
              Merge articles…
            </button>
            <button
              className="btn btn-ghost"
              style={{ width: "auto" }}
              disabled={rerun.isPending}
              title="Discards manual edits and rebuilds every article from the statistical clusters"
              onClick={() => {
                if (confirm("Re-run the orchestrator? This discards manual edits and rebuilds all articles from the clustering."))
                  rerun.mutate();
              }}
            >
              {rerun.isPending ? "Starting…" : "Re-run orchestrator"}
            </button>
          </>
        )}
      </div>
      )}

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
            sessionId={sessionId}
            run={run}
            mergeMode={!isVA && mergeMode}
            mergeSel={mergeSel}
            toggleMerge={toggleMerge}
          />
        ))}
      </div>
    </div>
  );
}

function TopicGroup(p: {
  name: string;
  relationship: string;
  clusters: Cluster[];
  gaps: CoverageGap[];
  byCluster: Map<string, Keyword[]>;
  clusterName: (id: string) => string;
  sessionId: string;
  run: (fn: () => Promise<unknown>) => void;
  mergeMode: boolean;
  mergeSel: Set<string>;
  toggleMerge: (id: string) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="topic-group">
      <button className="topic-group-head" onClick={() => setOpen((o) => !o)}>
        <span className="tree-caret">{open ? "▼" : "▶"}</span>
        <span className="topic-group-name">{p.name}</span>
        <span className="badge">{p.relationship}</span>
        <span className="topic-group-count">{p.clusters.length} articles</span>
      </button>
      {open && (
        <div className="topic-group-body">
          {p.clusters.map((c) => (
            <ArticleRow
              key={c.id}
              cluster={c}
              keywords={p.byCluster.get(c.id) ?? []}
              siblings={p.clusters}
              clusterName={p.clusterName}
              sessionId={p.sessionId}
              run={p.run}
              mergeMode={p.mergeMode}
              merged={p.mergeSel.has(c.id)}
              toggleMerge={p.toggleMerge}
            />
          ))}
          {p.gaps.filter((g) => g.status !== "dismissed").map((g) => (
            <GapRow key={g.id} gap={g} run={p.run} />
          ))}
        </div>
      )}
    </div>
  );
}

function ArticleRow(p: {
  cluster: Cluster;
  keywords: Keyword[];
  siblings: Cluster[];
  clusterName: (id: string) => string;
  sessionId: string;
  run: (fn: () => Promise<unknown>) => void;
  mergeMode: boolean;
  merged: boolean;
  toggleMerge: (id: string) => void;
}) {
  const { cluster: c, keywords, run } = p;
  const { role } = useSession();
  const isVA = role === "va";
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(c.name);
  const [splitMode, setSplitMode] = useState(false);
  const [splitSel, setSplitSel] = useState<Set<string>>(new Set());

  const primary = keywords.find((k) => k.is_primary_for_cluster) ?? keywords.find((k) => k.id === c.primary_keyword_id);
  const supporting = keywords.filter((k) => k.id !== primary?.id);
  const links = c.peer_article_links ?? [];

  function saveName() {
    setRenaming(false);
    if (nameDraft.trim() && nameDraft !== c.name) run(() => editCluster(c.id, { name: nameDraft.trim() }));
  }
  function doSplit() {
    const ids = [...splitSel];
    if (!ids.length) return;
    const name = window.prompt("New article name:", "");
    if (!name) return;
    run(() => splitCluster(c.id, ids, name));
    setSplitMode(false);
    setSplitSel(new Set());
  }
  function toggleSplit(id: string) {
    const next = new Set(splitSel);
    next.has(id) ? next.delete(id) : next.add(id);
    setSplitSel(next);
  }

  return (
    <div className="article-row">
      <div className="article-head-wrap">
        {p.mergeMode && (
          <input type="checkbox" checked={p.merged} onChange={() => p.toggleMerge(c.id)} title="Select for merge" />
        )}
        <button className="article-head" onClick={() => setOpen((o) => !o)}>
          <span className="tree-caret">{open ? "▼" : "▶"}</span>
          {renaming ? (
            <input
              className="input inline-input"
              value={nameDraft}
              autoFocus
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={saveName}
              onKeyDown={(e) => e.key === "Enter" && saveName()}
            />
          ) : (
            <span
              className="article-name"
              onClick={(e) => { e.stopPropagation(); setNameDraft(c.name); setRenaming(true); }}
              title="Click to rename"
            >
              {c.name}
            </span>
          )}
          {c.intent && <span className="badge badge-rel">{c.intent}</span>}
          {c.is_gap_placeholder && <span className="badge badge-warn">gap placeholder</span>}
          <span className="topic-group-count">{keywords.length} kw</span>
        </button>
      </div>

      {open && (
        <div className="article-detail">
          <DetailLine label="Primary">
            {primary?.keyword ?? <span className="cell-muted">— (no primary)</span>}
          </DetailLine>

          <DetailLine label="Intent">
            {isVA ? (
              <span>{c.intent ?? "—"}</span>
            ) : (
              <select
                className="select inline-select"
                value={c.intent ?? "informational"}
                onChange={(e) => run(() => editCluster(c.id, { intent: e.target.value }))}
              >
                {INTENTS.map((i) => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>
            )}
          </DetailLine>

          <DetailLine label="Supporting">
            {supporting.length === 0 && <span className="cell-muted">none</span>}
            <div className="kw-edit-list">
              {supporting.map((k) => (
                <div key={k.id} className="kw-edit-row">
                  {splitMode && (
                    <input type="checkbox" checked={splitSel.has(k.id)} onChange={() => toggleSplit(k.id)} />
                  )}
                  <span className="kw-edit-text">{k.keyword}</span>
                  {!isVA && (
                    <button className="link-btn" onClick={() => run(() => promotePrimary(c.id, k.id))}>
                      make primary
                    </button>
                  )}
                  <select
                    className="select kw-move-select"
                    value=""
                    onChange={(e) => {
                      const v = e.target.value;
                      if (!v) return;
                      run(() => bulkKeywordMove(p.sessionId, [k.id], v === "__unassigned__" ? null : v));
                    }}
                  >
                    <option value="">move to…</option>
                    {p.siblings.filter((s) => s.id !== c.id).map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                    <option value="__unassigned__">Unassigned</option>
                  </select>
                </div>
              ))}
            </div>
          </DetailLine>

          {links.length > 0 && <DetailLine label="Links to">{links.map(p.clusterName).join(", ")}</DetailLine>}

          <div className="article-actions">
            {isVA ? (
              <RequestRestructure articleName={c.name} />
            ) : splitMode ? (
              <>
                <span className="muted">{splitSel.size} keyword(s) → new article</span>
                <button className="btn btn-primary" style={{ width: "auto" }} disabled={!splitSel.size} onClick={doSplit}>Create</button>
                <button className="btn btn-ghost" style={{ width: "auto" }} onClick={() => { setSplitMode(false); setSplitSel(new Set()); }}>Cancel</button>
              </>
            ) : (
              <>
                <button className="link-btn" onClick={() => setSplitMode(true)}>Split…</button>
                <button
                  className="link-btn link-danger"
                  onClick={() => {
                    if (confirm(`Delete "${c.name}"? Its keywords move to Unassigned.`))
                      run(() => deleteCluster(c.id));
                  }}
                >
                  Delete article
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function GapRow({ gap, run }: { gap: CoverageGap; run: (fn: () => Promise<unknown>) => void }) {
  const { role } = useSession();
  const isVA = role === "va";
  return (
    <div className="gap-row">
      <span className="gap-mark">⚠ Gap</span>
      <span>{gap.suggested_title}</span>
      {gap.rationale && <span className="cell-muted">— {gap.rationale}</span>}
      {gap.status === "pending" && !isVA ? (
        <span className="gap-actions">
          <button className="link-btn" onClick={() => run(() => acceptGap(gap.id))}>Accept</button>
          <button className="link-btn link-danger" onClick={() => run(() => dismissGap(gap.id))}>Dismiss</button>
        </span>
      ) : (
        <span className="badge">{gap.status}</span>
      )}
    </div>
  );
}

// Stub for the VA "Request restructure from Owner" action (PRD §10.2). The real
// owner notification / request queue lands with the approval workflow (M9); for
// now this just acknowledges the flag locally.
function RequestRestructure({ articleName }: { articleName: string }) {
  const [sent, setSent] = useState(false);
  if (sent) return <span className="muted">Flagged for owner review.</span>;
  return (
    <button
      className="link-btn"
      title="Owner notifications arrive with the approval workflow"
      onClick={() => {
        setSent(true);
        alert(`Restructure requested for "${articleName}". Owner review arrives in a later update.`);
      }}
    >
      Request restructure from Owner
    </button>
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
