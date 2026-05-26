import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAllSurvivingKeywords, getClusters, type Keyword } from "../../shared/api";
import { useSession } from "../SessionWorkspace";

type LengthBand = "all" | "short" | "mid" | "long";
type QuestionFilter = "all" | "q" | "nonq";
type SortCol = "keyword" | "topic" | "relevance" | "status";

const QUESTION_RE =
  /^(who|what|when|where|why|how|which|is|are|can|could|does|do|did|will|would|should)\b/i;

function wordCount(kw: string): number {
  return kw.trim().split(/\s+/).filter(Boolean).length;
}
function band(kw: string): Exclude<LengthBand, "all"> {
  const n = wordCount(kw);
  if (n <= 2) return "short";
  if (n <= 4) return "mid";
  return "long";
}
function isQuestion(kw: string): boolean {
  return kw.includes("?") || QUESTION_RE.test(kw.trim());
}

// Table View (PRD §9.1): every surviving keyword, sortable + filterable. Volume /
// KD / CPC render as "—" because metrics enrichment (§7.8) isn't built (it's
// optional in v1). Bulk row actions are editing — they arrive in M7b.
export function TableView() {
  const { sessionId, topics, topicName } = useSession();
  const keywords = useQuery({
    queryKey: ["keywords-all", sessionId],
    queryFn: () => getAllSurvivingKeywords(sessionId),
  });
  const clustersQ = useQuery({ queryKey: ["clusters", sessionId], queryFn: () => getClusters(sessionId) });

  const clusterName = useMemo(() => {
    const m = new Map<string, string>();
    clustersQ.data?.clusters.forEach((c) => m.set(c.id, c.name));
    return (id: string | null) => (id ? m.get(id) ?? "—" : "Unassigned");
  }, [clustersQ.data]);

  const allSources = useMemo(() => {
    const s = new Set<string>();
    keywords.data?.forEach((k) => k.sources.forEach((src) => s.add(src)));
    return [...s].sort();
  }, [keywords.data]);

  const [search, setSearch] = useState("");
  const [topicSel, setTopicSel] = useState<Set<string>>(new Set());
  const [sourceSel, setSourceSel] = useState<Set<string>>(new Set());
  const [clusterSel, setClusterSel] = useState<string>("all");
  const [lengthBand, setLengthBand] = useState<LengthBand>("all");
  const [question, setQuestion] = useState<QuestionFilter>("all");
  const [sort, setSort] = useState<{ col: SortCol; dir: 1 | -1 }>({ col: "relevance", dir: -1 });

  const filtered = useMemo(() => {
    let rows = keywords.data ?? [];
    const q = search.trim().toLowerCase();
    if (q) rows = rows.filter((k) => k.keyword.toLowerCase().includes(q));
    if (topicSel.size) rows = rows.filter((k) => topicSel.has(k.topic_id));
    if (sourceSel.size) rows = rows.filter((k) => k.sources.some((s) => sourceSel.has(s)));
    if (clusterSel !== "all")
      rows = rows.filter((k) => (clusterSel === "none" ? !k.cluster_id : k.cluster_id === clusterSel));
    if (lengthBand !== "all") rows = rows.filter((k) => band(k.keyword) === lengthBand);
    if (question !== "all")
      rows = rows.filter((k) => (question === "q" ? isQuestion(k.keyword) : !isQuestion(k.keyword)));

    const dir = sort.dir;
    return [...rows].sort((a, b) => {
      switch (sort.col) {
        case "keyword":
          return dir * a.keyword.localeCompare(b.keyword);
        case "topic":
          return dir * topicName(a.topic_id).localeCompare(topicName(b.topic_id));
        case "status":
          return dir * a.status.localeCompare(b.status);
        case "relevance":
          return dir * ((a.relevance_score ?? -1) - (b.relevance_score ?? -1));
      }
    });
  }, [keywords.data, search, topicSel, sourceSel, clusterSel, lengthBand, question, sort, topicName]);

  if (keywords.isLoading) return <p className="muted">Loading keywords…</p>;
  if (keywords.isError) return <p className="form-error">Failed to load keywords.</p>;

  const total = keywords.data?.length ?? 0;
  const CAP = 1500;
  const shown = filtered.slice(0, CAP);

  function setSortCol(col: SortCol) {
    setSort((s) => (s.col === col ? { col, dir: (s.dir * -1) as 1 | -1 } : { col, dir: col === "relevance" ? -1 : 1 }));
  }
  const arrow = (col: SortCol) => (sort.col === col ? (sort.dir === 1 ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="filter-bar">
        <input
          className="input"
          style={{ maxWidth: 240 }}
          placeholder="Search keywords…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="select" style={{ width: "auto" }} value={clusterSel} onChange={(e) => setClusterSel(e.target.value)}>
          <option value="all">All clusters</option>
          <option value="none">Unassigned</option>
          {clustersQ.data?.clusters.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select className="select" style={{ width: "auto" }} value={lengthBand} onChange={(e) => setLengthBand(e.target.value as LengthBand)}>
          <option value="all">Any length</option>
          <option value="short">Short-tail (1–2)</option>
          <option value="mid">Mid-tail (3–4)</option>
          <option value="long">Long-tail (5+)</option>
        </select>
        <select className="select" style={{ width: "auto" }} value={question} onChange={(e) => setQuestion(e.target.value as QuestionFilter)}>
          <option value="all">Questions & non</option>
          <option value="q">Questions only</option>
          <option value="nonq">Non-questions</option>
        </select>
      </div>

      <ChipRow label="Topics" items={topics.map((t) => ({ id: t.id, label: t.name }))} sel={topicSel} setSel={setTopicSel} />
      {allSources.length > 0 && (
        <ChipRow label="Sources" items={allSources.map((s) => ({ id: s, label: s }))} sel={sourceSel} setSel={setSourceSel} />
      )}

      <p className="muted" style={{ margin: "12px 0" }}>
        {filtered.length.toLocaleString()} of {total.toLocaleString()} keywords
        {filtered.length > CAP && ` · showing first ${CAP.toLocaleString()} — refine filters to narrow`}
      </p>

      <div className="table-scroll">
        <table className="kw-table">
          <thead>
            <tr>
              <th className="sortable" onClick={() => setSortCol("keyword")}>Keyword{arrow("keyword")}</th>
              <th className="sortable" onClick={() => setSortCol("topic")}>Topic{arrow("topic")}</th>
              <th>Cluster</th>
              <th>Source</th>
              <th>Vol</th>
              <th>KD</th>
              <th>CPC</th>
              <th className="sortable num" onClick={() => setSortCol("relevance")}>Rel{arrow("relevance")}</th>
              <th className="sortable" onClick={() => setSortCol("status")}>Status{arrow("status")}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((k) => (
              <Row key={k.id} k={k} topicName={topicName} clusterName={clusterName} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({
  k,
  topicName,
  clusterName,
}: {
  k: Keyword;
  topicName: (id: string) => string;
  clusterName: (id: string | null) => string;
}) {
  return (
    <tr>
      <td>
        {k.keyword}
        {k.is_primary_for_cluster && <span className="badge badge-rel" style={{ marginLeft: 6 }}>primary</span>}
      </td>
      <td className="cell-muted">{topicName(k.topic_id)}</td>
      <td className="cell-muted">{clusterName(k.cluster_id)}</td>
      <td className="cell-muted cell-sources">{k.sources.join(", ")}</td>
      <td className="num cell-muted">—</td>
      <td className="num cell-muted">—</td>
      <td className="num cell-muted">—</td>
      <td className="num">{k.relevance_score != null ? k.relevance_score.toFixed(2) : "—"}</td>
      <td><span className={"status-tag status-" + k.status}>{k.status}</span></td>
    </tr>
  );
}

function ChipRow({
  label,
  items,
  sel,
  setSel,
}: {
  label: string;
  items: { id: string; label: string }[];
  sel: Set<string>;
  setSel: (s: Set<string>) => void;
}) {
  function toggle(id: string) {
    const next = new Set(sel);
    next.has(id) ? next.delete(id) : next.add(id);
    setSel(next);
  }
  return (
    <div className="chip-row">
      <span className="chip-row-label">{label}</span>
      {items.map((it) => (
        <button
          key={it.id}
          className={"chip" + (sel.has(it.id) ? " chip-on" : "")}
          onClick={() => toggle(it.id)}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
