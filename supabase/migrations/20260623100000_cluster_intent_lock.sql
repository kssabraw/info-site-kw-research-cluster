-- M14 follow-up — cluster intent reconciliation with the Brief Generator.
--
-- Two behaviors:
--  1. SYNC: when an article/brief is generated, the brief's freshly-classified intent_type
--     is written back to clusters.intent so the Cluster-view dropdown reflects reality
--     instead of the stale article-planning (M5) value. This is a system write — it does
--     NOT set is_user_edited / intent_locked.
--  2. OVERRIDE: when the owner changes the intent dropdown, update_cluster sets
--     intent_locked = true; a locked intent is passed to the Brief Generator as an
--     authoritative override (the brief honors it instead of re-classifying).
--
-- intent_locked distinguishes a deliberate owner choice from the (coarse) is_user_edited
-- flag, which any edit (rename / move / etc.) already trips.

alter table fanout.clusters add column intent_locked boolean not null default false;
