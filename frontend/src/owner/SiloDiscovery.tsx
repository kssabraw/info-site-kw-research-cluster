import { useState, type FormEvent } from "react";
import {
  addTopic,
  createSession,
  deleteTopic,
  disambiguateSession,
  editTopic,
  finalizeSilos,
  getSession,
  overrideAudience,
  type RelationshipType,
  type Silo,
  type SiloDiscovery as Discovery,
} from "../shared/api";
import {
  RELATIONSHIP_LABELS,
  RELATIONSHIP_OPTIONS,
} from "../shared/relationshipTypes";

type Step = "form" | "loading" | "disambiguation" | "review" | "done";

export function SiloDiscovery({ onExit }: { onExit: () => void }) {
  const [step, setStep] = useState<Step>("form");
  const [error, setError] = useState<string | null>(null);
  const [discovery, setDiscovery] = useState<Discovery | null>(null);

  // form state
  const [seed, setSeed] = useState("");
  const [audience, setAudience] = useState("");
  const [disambHint, setDisambHint] = useState("");
  const [topicCount, setTopicCount] = useState(5);
  const [mode, setMode] = useState<"standard" | "comprehensive">("standard");
  const [showOptional, setShowOptional] = useState(false);

  function applyResult(d: Discovery) {
    setDiscovery(d);
    setStep(d.needs_disambiguation ? "disambiguation" : "review");
  }

  async function reload(id: string) {
    setDiscovery(await getSession(id));
  }

  async function onSubmitSeed(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setStep("loading");
    try {
      const d = await createSession({
        seed_keyword: seed.trim(),
        audience_hint: audience.trim() || undefined,
        disambiguation_hint: disambHint.trim() || undefined,
        topic_count: topicCount,
        coverage_mode: mode,
      });
      applyResult(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discovery failed");
      setStep("form");
    }
  }

  async function pickInterpretation(choice: string) {
    if (!discovery) return;
    setError(null);
    setStep("loading");
    try {
      applyResult(await disambiguateSession(discovery.session_id, choice));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      setStep("disambiguation");
    }
  }

  async function onFinalize() {
    if (!discovery) return;
    setError(null);
    try {
      await finalizeSilos(discovery.session_id);
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Finalize failed");
    }
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

        {step === "form" && (
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

        {step === "loading" && (
          <div className="state-center" style={{ minHeight: "40vh" }}>
            Discovering silos — grounding, demand sample, and competitor structure…
          </div>
        )}

        {step === "disambiguation" && discovery && (
          <Disambiguation
            seed={seed}
            interpretations={discovery.interpretations}
            onPick={pickInterpretation}
          />
        )}

        {step === "review" && discovery && (
          <Review
            discovery={discovery}
            onReload={() => reload(discovery.session_id)}
            onFinalize={onFinalize}
            setError={setError}
          />
        )}

        {step === "done" && (
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
  discovery: Discovery;
  onReload: () => Promise<void>;
  onFinalize: () => void;
  setError: (v: string | null) => void;
}) {
  const { discovery } = p;
  const [audienceEdit, setAudienceEdit] = useState(discovery.detected_audience ?? "");
  const [adding, setAdding] = useState(false);

  async function guard(fn: () => Promise<unknown>) {
    p.setError(null);
    try {
      await fn();
      await p.onReload();
    } catch (err) {
      p.setError(err instanceof Error ? err.message : "Action failed");
    }
  }

  return (
    <>
      <h1 className="page-title">Review proposed silos</h1>

      {discovery.degraded_notes.map((note) => (
        <div className="banner" key={note}>
          {note}
        </div>
      ))}

      <div className="audience-bar">
        <span>Audience:</span>
        <input
          className="input"
          style={{ maxWidth: 360 }}
          value={audienceEdit}
          onChange={(e) => setAudienceEdit(e.target.value)}
        />
        <button
          className="btn btn-ghost"
          onClick={() =>
            guard(() => overrideAudience(discovery.session_id, audienceEdit.trim()))
          }
        >
          Save
        </button>
      </div>

      {discovery.silos.map((silo) => (
        <SiloCard key={silo.id} silo={silo} onChange={guard} />
      ))}

      {!adding && (
        <button className="link-btn" onClick={() => setAdding(true)}>
          + Add custom silo
        </button>
      )}
      {adding && (
        <AddSiloForm
          sessionId={discovery.session_id}
          onClose={() => setAdding(false)}
          onSaved={p.onReload}
          setError={p.setError}
        />
      )}

      <div className="toolbar">
        <span className="muted">{discovery.silos.length} silos</span>
        <button
          className="btn btn-primary"
          style={{ width: "auto" }}
          disabled={discovery.silos.length === 0}
          onClick={p.onFinalize}
        >
          Continue
        </button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
function SiloCard(p: { silo: Silo; onChange: (fn: () => Promise<unknown>) => void }) {
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
              p.onChange(() =>
                editTopic(silo.id, {
                  name: name.trim(),
                  rationale,
                  relationship_type: rel,
                }),
              );
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
          <button className="link-btn" onClick={() => p.onChange(() => deleteTopic(silo.id))}>
            Remove
          </button>
        </div>
      </div>
      <div className="silo-badges">
        <span className="badge badge-rel">{RELATIONSHIP_LABELS[silo.relationship_type]}</span>
        {silo.is_broader_class && (
          <span className="badge badge-warn" title="Category-level coverage; include only if niche-strategic">
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
function AddSiloForm(p: {
  sessionId: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
  setError: (v: string | null) => void;
}) {
  const [name, setName] = useState("");
  const [rationale, setRationale] = useState("");
  const [rel, setRel] = useState<RelationshipType>("property_or_mechanism");

  async function save() {
    p.setError(null);
    try {
      await addTopic(p.sessionId, {
        name: name.trim(),
        rationale: rationale.trim() || undefined,
        relationship_type: rel,
      });
      await p.onSaved();
      p.onClose();
    } catch (err) {
      p.setError(err instanceof Error ? err.message : "Failed to add silo");
    }
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
        <button className="link-btn" disabled={!name.trim()} onClick={save}>
          Add silo
        </button>
        <button className="link-btn" onClick={p.onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}
