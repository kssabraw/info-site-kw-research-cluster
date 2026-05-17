# Row Level Security Policies

This directory is **deliberately empty**. RLS is enabled on every
multi-tenant table in `schema/schema.sql` (and `schema/migrations/0001_initial_schema.sql`),
but no policies are defined.

## Why empty?

For the current single-user CLI pipeline, the only database connection
uses Supabase's `service_role` key, which bypasses RLS entirely. Adding
policies would have zero runtime effect today and would require
designing the user/site mapping before any real user exists. See
[`docs/decisions-log.md` ADR-013](../../docs/decisions-log.md).

The current posture: **service_role connections work normally;
everything else gets zero rows back.** Intentional, not an oversight.

## When must policies be added?

The first commit that introduces any of the following must also land
a policy set here AND a migration that applies it:

1. A `site_users` (or similar) table mapping users to sites — i.e.,
   anyone is granted access to a specific subset of sites rather than
   "all of them via service_role."
2. Any code path that connects to the database with a non-`service_role`
   key (typical case: the team UI authenticating via Supabase auth).
3. The team UI itself (web dashboard) — even if it uses service_role
   server-side, the moment users hit it directly via Supabase JS with
   the anon key, policies are mandatory.

Reviewers should reject any commit meeting one of these conditions
that does not also add policies in the same change.

## Contract for the eventual policy set

When policies are written, they must satisfy at minimum:

- **Read your own site:** users can SELECT rows where `site_id` is
  in their authorized site list.
- **Write your own site:** users can INSERT/UPDATE/DELETE rows where
  `site_id` is in their authorized site list AND the row's `site_id`
  is in that list (prevents inserting a row for a site you don't own).
- **No implicit cross-site reads:** queries that don't filter by
  `site_id` (or that the planner couldn't prove are tenant-bounded)
  should return zero rows under RLS, not data from another site.
- **Denormalized `site_id` consistency:** for child tables
  (`keyword_serps`, `keyword_embeddings`, `cluster_members`,
  `topic_keywords`, `topic_dependencies`, `topic_relationships`),
  policies should compare the row's `site_id` against the user's
  authorized list directly — not chase through the parent. This is
  why we denormalize.

## File layout (when populated)

```
schema/policies/
├── README.md               (this file)
├── 0001_baseline_policies.sql    (the first policy set)
└── ...
```

Policy SQL files follow the same naming convention as
`schema/migrations/`, and ARE migrations — they must be applied in
order and committed alongside the schema change that necessitates them.
