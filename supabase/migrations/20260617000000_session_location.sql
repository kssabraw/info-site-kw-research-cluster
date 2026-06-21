-- Per-country locale (E1, 2026-06-17) — international client support.
--
-- DataForSEO localizes by `location_code`; the `language_code` stays "en" for
-- every supported English market, so a single per-session location_code is all
-- the pipeline needs. Supported markets (Google/DataForSEO country codes,
-- 2000 + ISO-3166 numeric):
--   USA 2840 · UK 2826 · Canada 2124 · Australia 2036 · New Zealand 2554
--
-- Existing rows default to US (2840) — they *were* US runs, so no backfill is
-- required. The check constraint is defence-in-depth: the API layer also
-- allow-lists these codes, but service-role writes bypass RLS/app validation,
-- so the DB enforces the set too. Adding a market later = extend this list + the
-- API allow-list + the frontend dropdown map.
alter table fanout.sessions
  add column location_code int not null default 2840
    constraint sessions_location_code_supported
      check (location_code in (2840, 2826, 2124, 2036, 2554));
