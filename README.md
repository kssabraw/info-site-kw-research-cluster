# info-site-kw-research-cluster

Fresh start — this repository was reset on 2026-05-21.

The previous implementation (a 12-phase multi-tenant keyword discovery
and clustering pipeline) was archived and removed. Nothing from the old
codebase remains in this history.

## Recovering the previous version

A complete snapshot of the old codebase — all commits, the full phase
pipeline, 39 ADRs, and tests — was exported as a git bundle before the
reset. To restore it:

```bash
git clone info-site-kw-research-cluster-full-history.bundle recovered-repo
```

The old Supabase `kw_clustering` schema and all its data were also
dropped. The accompanying CSV exports (clusters + topics) captured the
last output before teardown.

## Next steps

This is an intentionally empty slate. Add the new project structure here.
