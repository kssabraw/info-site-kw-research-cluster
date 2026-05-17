# Architecture

Detailed system design for the multi-tenant keyword discovery and
clustering pipeline. This document is populated as architectural
patterns are established during implementation.

For strategic context and decisions, see
[PROJECT_BRIEF.md](../PROJECT_BRIEF.md) and
[docs/decisions-and-reasoning.md](decisions-and-reasoning.md).

For per-phase specifications, see
[docs/pipeline-phases.md](pipeline-phases.md).

---

## System Overview

*To be documented during implementation.*

This section will contain:
- High-level data flow diagram
- Component relationships
- Pipeline orchestration approach
- Multi-tenant request flow

---

## Multi-Tenancy

*To be documented during implementation.*

This section will cover:
- How `site_id` flows through the pipeline
- Database isolation patterns
- Row Level Security policy structure (deferred until team UI)
- Cross-site queries (when allowed, how implemented)

---

## Database Layer

*To be documented during implementation.*

This section will cover:
- Database client structure
- Connection pooling approach
- Transaction boundaries
- Query patterns and conventions
- pgvector usage patterns

---

## API Client Patterns

*To be documented during implementation.*

This section will cover:
- DataForSEO client structure
- OpenAI client structure
- Anthropic client structure
- Retry and backoff patterns
- Rate limit handling
- Cost tracking integration

---

## Configuration System

*To be documented during implementation.*

This section will cover:
- YAML config loading and validation
- Pydantic models for config structures
- Template system (when introduced)
- Per-site vs global config handling
- Environment variable integration

---

## Phase Orchestration

*To be documented during implementation.*

This section will cover:
- Phase module structure
- Job tracking decorator pattern
- Phase dependency rules
- Re-run and idempotency behavior
- CLI integration

---

## Error Handling

*To be documented during implementation.*

This section will cover:
- Error categorization (recoverable vs fatal)
- Logging conventions
- Error reporting in pipeline_jobs
- User-facing error messages
- Recovery procedures

---

## Cost Management

*To be documented during implementation.*

This section will cover:
- Cost estimation per phase
- Cost guardrails (max_run_cost_usd)
- Cost tracking in pipeline_jobs
- Cost reporting and visibility

---

## Testing Approach

*To be documented during implementation.*

This section will cover:
- Manual testing approach for MVP
- Test database setup
- Sample data generation
- Future test framework (deferred until team adoption)

---

## How This Document Is Maintained

This document captures architectural patterns as they're established.
It should be updated when:

- A new cross-cutting pattern is established (error handling, logging,
  API client structure)
- A pattern is changed (breaking change, refactor)
- A new component is added (new utility, new integration)

Don't update for:
- Phase-specific details (those go in pipeline-phases.md)
- Specific decisions and tradeoffs (those go in decisions-log.md)
- Schema details (those go in database-schema.md)

This document is for understanding HOW the system is built. The why is
elsewhere; the what-by-phase is elsewhere.
