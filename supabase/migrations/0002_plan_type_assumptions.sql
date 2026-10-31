-- v2: plan-first assumptions and plan types. Safe to re-run.
alter table public.trip_requests add column if not exists assumed_slots jsonb not null default '[]'::jsonb;
alter table public.trip_requests add column if not exists plan_type varchar(12) not null default 'intercity';
alter table public.trips add column if not exists plan_type varchar(12) not null default 'intercity';
