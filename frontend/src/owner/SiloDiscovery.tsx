import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addTopic,
  createSession,
  deleteTopic,
  disambiguateSession,
  editTopic,
  finalizeSilos,
  getSession,
  overrideAudience,
  type AddTopicBody,
  type EditTopicBody,
  type RelationshipType,
  type Silo,
  type SiloDiscovery as Discovery,
} from "../shared/api";
import {
  RELATIONSHIP_LABELS,
  RELATIONSHIP_OPTIONS,
} from "../shared/relationshipTypes";

type Step = "form" | "disambiguation" | "review" | "done";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong");

export function SiloDiscovery({ onExit }: { onExit: () => void }) {
  const qc = useQueryClient();
  const [step, setStep] = useState<Step>("form");
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  // Degraded-mode notes belong to the discovery run, so keep them in state —
  // refetches (after silo edits) must not clear the banners.
  const [degradedNotes, setDegradedNotes] = useState<string[]>([]);
  const [interpretations, setInterpretations] = useState<string[]>([]);

  // form state
  const [seed, setSeed] = useState("");
  const [audience, setAudience] = useState("");
  const [disambHint, setDisambHint] = useState("");
  const [topicCount, setTopicCount] = useState(5);
  const [mode, setMode] = useState<"standard" | "comprehensive">("standard");
  const [showOptional, setShowOptional] = useState(false);

  function applyResult(d: Discovery) {
    setSessionId(d.session_id);
    setDegradedNotes(d.degraded_notes);
    if (d.needs_disambiguation) {
      setInterpretations(d.interpretations);
      setStep("disambiguation");
    } else {
      // Seed the cache so Review renders immediately without an extra fetch.
      qc.setQueryData(["session", d.session_id], d);
      setStep("review");
    }
  }

  const createMut = useMutation({
    mutationFn: createSession,
    onSuccess: applyResult,
    onError: (e) => setError(msg(e)),
  });
  const disambigMut = useMutation({
    mutationFn: (choice: string) => disambiguateSession(sessionId!, choice),
    onSuccess: applyResult,
    onError: (e) => setError(msg(e)),
  });
  const finalizeMut = useMutation({
    mutationFn: () => finalizeSilos(sessionId!),
    onSuccess: () => setStep("done"),
    onError: (e) => setError(msg(e)),
  });

  const busy = createMut.isPending || disambigMut.isPending;

  function onSubmitSeed(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createMut.mutate({
      seed_keyword: seed.trim(),
      audience_hint: audience.trim() || undefined,
      disambiguation_hint: disambHint.trim() || undefined,
      topic_count: topicCount,
      coverage_mode: mode,
    });
  }

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Topic Fanout</span>
        </div>
        <button className="btn btn-ghost" onClick={onExit}>
          Back to projects
        </button>
      </header>

      <main className="content">
        {error && <p className="form-error">{error}</p>}

        {busy && <DiscoveryProgress />}

        {!busy && step === "form" && (
          <SeedForm
            {...{
              seed,
              setSeed,
              audience,
              setAudience,
              disambHint,
              setDisambHint,
              topicCount,
              setTopicCount,
              mode,
              setMode,
              showOptional,
              setShowOptional,
              onSubmit: onSubmitSeed,
            }}
          />
        )}

        {!busy && step === "disambiguation" && (
          <Disambiguation
            seed={seed}
            interpretations={interpretations}
            onPick={(choice) => {
              setError(null);
              disambigMut.mutate(choice);
            }}
          />
        )}

        {!busy && step === "review" && sessionId && (
          <Review
            sessionId={sessionId}
            degradedNotes={degradedNotes}
            finalizing={finalizeMut.isPending}
            onFinalize={() => {
              setError(null);
              finalizeMut.mutate();
            }}
            setError={setError}
          />
        )}

        {!busy && step === "done" && (
          <div className="card">
            <h1 className="page-title">Silos finalized</h1>
            <p className="muted">
              Your silos are locked and embedded. Keyword expansion runs in the next
              milestone (M3).
            </p>
            <div className="toolbar">
              <span />
              <button className="btn btn-primary" style={{ width: "auto" }} onClick={onExit}>
                Done
              </button>
            </div>
          </div>
        )}
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// The grounding→proposal pipeline runs as a single request, so there's no live
// per-step signal. We show an elapsed timer, a soft progress bar, and step the
// caption through the known stages (PRD §7.1.1) by elapsed time.
const DISCOVERY_STAGES: { until: number; label: string }[] = [
  { until: 10, label: "Reading top-ranking content for your seed" },
  { until: 16, label: "Sampling search demand" },
  { until: 22, label: "Analyzing competitor site structure" },
  { until: Infinity, label: "Proposing silos" },
];
const DISCOVERY_TARGET_S = 35;

function DiscoveryProgress() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const stage =
    DISCOVERY_STAGES.find((s) => elapsed < s.until) ??
    DISCOVERY_STAGES[DISCOVERY_STAGES.length - 1];
  // Approach but never reach 100% until the request actually resolves.
  const pct = Math.min(92, Math.round((elapsed / DISCOVERY_TARGET_S) * 100));

  return (
    <div className="progress-wrap">
      <div className="spinner" aria-hidden="true" />
      <div className="progress-stage">{stage.label}…</div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="progress-meta">
        Elapsed {elapsed}s · usually 20–40 seconds
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
function SeedForm(p: {
  seed: string;
  setSeed: (v: string) => void;
  audience: string;
  setAudience: (v: string) => void;
  disambHint: string;
  setDisambHint: (v: string) => void;
  topicCount: number;
  setTopicCount: (v: number) => void;
  mode: "standard" | "comprehensive";
  setMode: (v: "standard" | "comprehensive") => void;
  showOptional: boolean;
  setShowOptional: (v: boolean) => void;
  onSubmit: (e: FormEvent) => void;
}) {
  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h1 className="page-title">New research session</h1>
      <form onSubmit={p.onSubmit}>
        <label className="field">
          <span className="field-label">Seed keyword</span>
          <input
            className="input"
            value={p.seed}
            onChange={(e) => p.setSeed(e.target.value)}
            placeholder="e.g. retatrutide"
            maxLength={200}
            required
          />
        </label>

        {!p.showOptional && (
          <div className="collapse-link">
            <button type="button" className="link-btn" onClick={() => p.setShowOptional(true)}>
              + Add audience or disambiguation hint
            </button>
          </div>
        )}
        {p.showOptional && (
          <>
            <label className="field">
              <span className="field-label">Audience (optional)</span>
              <input
                className="input"
                value={p.audience}
                onChange={(e) => p.setAudience(e.target.value)}
                placeholder="e.g. clinicians researching prescribing decisions"
              />
            </label>
            <label className="field">
              <span className="field-label">Disambiguation (optional)</span>
              <input
                className="input"
                value={p.disambHint}
                onChange={(e) => p.setDisambHint(e.target.value)}
                placeholder="e.g. the chemical element, not the planet"
              />
            </label>
          </>
        )}

        <div className="row">
          <label className="field">
            <span className="field-label">Silos: {p.topicCount}</span>
            <input
              type="range"
              min={3}
              max={10}
              value={p.topicCount}
              onChange={(e) => p.setTopicCount(Number(e.target.value))}
              style={{ width: "100%" }}
            />
          </label>
          <label className="field">
            <span className="field-label">Coverage mode</span>
            <select
              className="select"
              value={p.mode}
              onChange={(e) => p.setMode(e.target.value as "standard" | "comprehensive")}
            >
              <option value="standard">Standard (top 5)</option>
              <option value="comprehensive">Comprehensive (top 10)</option>
            </select>
          </label>
        </div>

        <button className="btn btn-primary" type="submit" style={{ marginTop: 8 }}>
          Discover silos
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
function Disambiguation(p: {
  seed: string;
  interpretations: string[];
  onPick: (choice: string) => void;
}) {
  const [custom, setCustom] = useState("");
  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h1 className="page-title">Which “{p.seed}”?</h1>
      <p className="muted">
        This seed looks ambiguous. Pick the intended interpretation so the silos
        stay on-topic.
      </p>
      <div className="interp-list">
        {p.interpretations.map((i) => (
          <button key={i} className="interp-option" onClick={() => p.onPick(i)}>
            {i}
          </button>
        ))}
      </div>
      <label className="field">
        <span className="field-label">Or describe it yourself</span>
        <div className="row">
          <input
            className="input"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="e.g. the chemical element"
          />
          <button
            className="btn btn-primary"
            style={{ width: "auto" }}
            disabled={!custom.trim()}
            onClick={() => p.onPick(custom.trim())}
          >
            Use this
          </button>
        </div>
      </label>
    </div>
  );
}

// ---------------------------------------------------------------------------
function Review(p: {
  sessionId: string;
  degradedNotes: string[];
  finalizing: boolean;
  onFinalize: () => void;
  setError: (v: string | null) => void;
}) {
  const qc = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: ["session", p.sessionId],
    queryFn: () => getSession(p.sessionId),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["session", p.sessionId] });
  const onErr = (e: unknown) => p.setError(e instanceof Error ? e.message : "Action failed");

  const audienceMut = useMutation({
    mutationFn: (a: string) => overrideAudience(p.sessionId, a),
    onSuccess: invalidate,
    onError: onErr,
  });
  const addMut = useMutation({
    mutationFn: (b: AddTopicBody) => addTopic(p.sessionId, b),
    onSuccess: invalidate,
    onError: onErr,
  });
  const editMut = useMutation({
    mutationFn: (v: { id: string; body: EditTopicBody }) => editTopic(v.id, v.body),
    onSuccess: invalidate,
    onError: onErr,
  });
  const delMut = useMutation({
    mutationFn: (id: string) => deleteTopic(id),
    onSuccess: invalidate,
    onError: onErr,
  });

  const data = sessionQuery.data;
  const silos = data?.silos ?? [];
  const [audienceEdit, setAudienceEdit] = useState<string | null>(null);
  const audienceValue = audienceEdit ?? data?.detected_audience ?? "";

  if (sessionQuery.isLoading) {
    return <div className="state-center">Loading silos…</div>;
  }

  return (
    <>
      <h1 className="page-title">Review proposed silos</h1>

      {p.degradedNotes.map((note) => (
        <div className="banner" key={note}>
          {note}
        </div>
      ))}

      <div className="audience-bar">
        <span>Audience:</span>
        <input
          className="input"
          style={{ maxWidth: 360 }}
          value={audienceValue}
          onChange={(e) => setAudienceEdit(e.target.value)}
        />
        <button
          className="btn btn-ghost"
          disabled={audienceMut.isPending}
          onClick={() => audienceMut.mutate(audienceValue.trim())}
        >
          Save
        </button>
      </div>

      {silos.map((silo) => (
        <SiloCard
          key={silo.id}
          silo={silo}
          onEdit={(body) => editMut.mutate({ id: silo.id, body })}
          onDelete={() => delMut.mutate(silo.id)}
        />
      ))}

      <AddSiloRow onAdd={(body) => addMut.mutate(body)} adding={addMut.isPending} />

      <div className="toolbar">
        <span className="muted">{silos.length} silos</span>
        <button
          className="btn btn-primary"
          style={{ width: "auto" }}
          disabled={silos.length === 0 || p.finalizing}
          onClick={p.onFinalize}
        >
          {p.finalizing ? "Finalizing…" : "Continue"}
        </button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
function SiloCard(p: {
  silo: Silo;
  onEdit: (body: EditTopicBody) => void;
  onDelete: () => void;
}) {
  const { silo } = p;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(silo.name);
  const [rationale, setRationale] = useState(silo.rationale ?? "");
  const [rel, setRel] = useState<RelationshipType>(silo.relationship_type);

  if (editing) {
    return (
      <div className="silo-card">
        <label className="field">
          <span className="field-label">Name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">Rationale</span>
          <textarea
            className="textarea"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field-label">Relationship</span>
          <select
            className="select"
            value={rel}
            onChange={(e) => setRel(e.target.value as RelationshipType)}
          >
            {RELATIONSHIP_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {RELATIONSHIP_LABELS[o]}
              </option>
            ))}
          </select>
        </label>
        <div className="silo-actions">
          <button
            className="link-btn"
            onClick={() => {
              p.onEdit({ name: name.trim(), rationale, relationship_type: rel });
              setEditing(false);
            }}
          >
            Save
          </button>
          <button className="link-btn" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="silo-card">
      <div className="silo-head">
        <p className="silo-name">{silo.name}</p>
        <div className="silo-actions">
          <button className="link-btn" onClick={() => setEditing(true)}>
            Edit
          </button>
          <button className="link-btn" onClick={p.onDelete}>
            Remove
          </button>
        </div>
      </div>
      <div className="silo-badges">
        <span className="badge badge-rel">{RELATIONSHIP_LABELS[silo.relationship_type]}</span>
        {silo.is_broader_class && (
          <span
            className="badge badge-warn"
            title="Category-level coverage; include only if niche-strategic"
          >
            broader class
          </span>
        )}
        {silo.source !== "llm_proposed" && <span className="badge">{silo.source}</span>}
      </div>
      {silo.rationale && <p className="silo-text">{silo.rationale}</p>}
      {silo.supporting_evidence && (
        <p className="silo-evidence">Evidence: {silo.supporting_evidence}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function AddSiloRow(p: { onAdd: (body: AddTopicBody) => void; adding: boolean }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [rationale, setRationale] = useState("");
  const [rel, setRel] = useState<RelationshipType>("property_or_mechanism");

  if (!open) {
    return (
      <button className="link-btn" onClick={() => setOpen(true)}>
        + Add custom silo
      </button>
    );
  }

  return (
    <div className="inline-form">
      <label className="field">
        <span className="field-label">Name</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        <span className="field-label">Rationale (optional)</span>
        <textarea
          className="textarea"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
      </label>
      <label className="field">
        <span className="field-label">Relationship</span>
        <select
          className="select"
          value={rel}
          onChange={(e) => setRel(e.target.value as RelationshipType)}
        >
          {RELATIONSHIP_OPTIONS.map((o) => (
            <option key={o} value={o}>
              {RELATIONSHIP_LABELS[o]}
            </option>
          ))}
        </select>
      </label>
      <div className="silo-actions">
        <button
          className="link-btn"
          disabled={!name.trim() || p.adding}
          onClick={() => {
            p.onAdd({
              name: name.trim(),
              rationale: rationale.trim() || undefined,
              relationship_type: rel,
            });
            setOpen(false);
            setName("");
            setRationale("");
          }}
        >
          Add silo
        </button>
        <button className="link-btn" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}
