-- db/schema.sql
create table if not exists responses (
  request_id uuid primary key,
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'completed', 'failed')),
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists responses_status_idx on responses (status);