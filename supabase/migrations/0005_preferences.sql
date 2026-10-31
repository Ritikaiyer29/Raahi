-- Travel-agent preferences (flight or train, hotel, trip type) and the questions asked last turn. Safe to re-run.
alter table public.trip_requests add column if not exists preferences jsonb not null default '{}'::jsonb;
