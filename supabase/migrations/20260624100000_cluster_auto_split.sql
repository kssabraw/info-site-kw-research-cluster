-- M13/M15 follow-up — auto-split recursion guard.
--
-- When the coverage audit's uncovered keywords are confirmed into their own articles, those
-- new clusters are flagged auto_split so their *own* write doesn't re-prompt to split again
-- (terminates the cascade; a tight 0.85 group's keywords are covered by its own brief anyway).

alter table fanout.clusters add column auto_split boolean not null default false;
