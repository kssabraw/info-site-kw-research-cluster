-- M15 review fix — atomic session-cost increment (concurrent-writer safe).
--
-- The cost meter previously read actual_cost_usd once at job start and wrote base+total. That
-- is correct only under the "one writer per session" guard (try_mark_running) the pipeline
-- jobs hold — but the M15 scheduler drains up to `cap` article writes of the SAME session
-- concurrently, so the read-modify-write lost updates (a 3-at-a-time batch could under-report
-- cost by ~2/3). This RPC makes the flush an atomic, row-locked delta increment: each writer
-- adds only its own spend since its last flush, so concurrent flushes accumulate correctly.

create or replace function fanout.increment_session_cost(
  p_session_id uuid, p_delta numeric, p_breakdown_delta jsonb
) returns void language plpgsql as $$
declare
  cur jsonb;
  k   text;
  v   numeric;
begin
  -- Row lock serializes concurrent increments on this session (delta merge is read-modify-write).
  select coalesce(cost_breakdown, '{}'::jsonb) into cur
    from fanout.sessions where id = p_session_id for update;
  if not found then
    return;
  end if;
  for k, v in select key, value::numeric from jsonb_each_text(coalesce(p_breakdown_delta, '{}'::jsonb)) loop
    cur := jsonb_set(cur, array[k], to_jsonb(round(coalesce((cur->>k)::numeric, 0) + v, 6)));
  end loop;
  update fanout.sessions
     set actual_cost_usd = round(coalesce(actual_cost_usd, 0) + p_delta, 6),
         cost_breakdown  = cur
   where id = p_session_id;
end;
$$;

grant execute on function fanout.increment_session_cost(uuid, numeric, jsonb) to service_role;
