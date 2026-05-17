# Decisions Log

Architecture Decision Records (ADRs) for decisions made during
implementation. Each entry documents a specific decision, its context,
and consequences.

For architectural philosophy and high-level reasoning, see
[docs/decisions-and-reasoning.md](decisions-and-reasoning.md).

This log captures granular decisions that emerge during implementation:
- Specific parameter values (e.g., "min_cluster_size set to 5")
- Implementation patterns chosen during coding
- Tradeoffs evaluated mid-build
- Refinements to original design

---

## ADR Format

Each ADR follows this structure:
ADR-NNN: Title
Date: YYYY-MM-DD
Status: Proposed | Accepted | Deprecated | Superseded
Context
What problem are we solving? What constraints exist?
Decision
What was decided?
Consequences
What follows from this decision? Both positive and negative.
Alternatives Considered
What else was evaluated?

---

## Existing ADRs

ADRs are added as decisions are made during implementation. The
strategic decisions made before implementation began are captured in
[docs/decisions-and-reasoning.md](decisions-and-reasoning.md), not here.

This log starts at ADR-001 for decisions made from build start onward.

---

## How This Document Is Maintained

Add a new ADR when:

- A non-obvious technical choice is made
- A parameter is tuned away from default with reasoning
- An implementation pattern is established that future code should follow
- A tradeoff is evaluated and resolved

Don't add ADRs for:

- Obvious technical choices (e.g., "use UTF-8 encoding")
- Strategic decisions (those belong in decisions-and-reasoning.md)
- Phase implementation details (those belong in pipeline-phases.md)

ADRs are numbered sequentially. Don't renumber when adding new ones.
If an ADR is superseded, mark its status and link to the new ADR.
