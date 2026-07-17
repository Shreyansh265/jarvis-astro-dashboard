-- ===================================================================
-- JARVIS Astro Dashboard — Supabase schema
-- Paste this into Supabase Dashboard -> SQL Editor -> New query -> Run
-- ===================================================================

-- Your real portfolio (stocks you manually add/remove)
create table if not exists portfolio (
    id bigint generated always as identity primary key,
    ticker text not null,
    quantity numeric not null default 1,
    buy_price numeric not null,
    buy_date date not null default current_date,
    exchange text not null default 'NYSE',   -- 'NYSE' or 'TSX'
    notes text,
    created_at timestamptz not null default now()
);

-- Daily planetary positions log (so we always have history, even before backtests run)
create table if not exists planetary_log (
    id bigint generated always as identity primary key,
    date date not null unique,
    positions jsonb not null,
    aspects jsonb not null,
    created_at timestamptz not null default now()
);

-- Every sector/stock signal the engine has ever generated
create table if not exists predictions (
    id bigint generated always as identity primary key,
    date date not null,
    sector text not null,
    ticker text not null,
    direction text not null,              -- 'bullish' | 'bearish' | 'neutral'
    possibility_indicator numeric not null,
    reasons jsonb not null,
    contributing_planets jsonb not null,
    price_at_prediction numeric,
    reviewed boolean not null default false,
    outcome_direction text,               -- filled in by weekly review
    outcome_pct_change numeric,
    was_correct boolean,
    created_at timestamptz not null default now()
);

-- Learned weight per planet-rule, updated by weekly review based on real accuracy
create table if not exists rule_weights (
    planet text primary key,
    weight numeric not null default 0.5,
    correct_count integer not null default 0,
    incorrect_count integer not null default 0,
    last_updated timestamptz not null default now()
);

-- Paper trading bot: $20,000 simulated account
create table if not exists paper_account (
    id bigint generated always as identity primary key,
    cash numeric not null default 20000,
    updated_at timestamptz not null default now()
);
insert into paper_account (cash) select 20000 where not exists (select 1 from paper_account);

create table if not exists paper_trades (
    id bigint generated always as identity primary key,
    ticker text not null,
    sector text not null,
    action text not null,                 -- 'BUY' | 'SELL'
    quantity numeric not null,
    price numeric not null,
    reasoning text not null,
    possibility_indicator numeric,
    trade_date date not null default current_date,
    linked_buy_trade_id bigint references paper_trades(id),
    pnl numeric,                          -- filled in on the SELL row
    pnl_pct numeric,
    created_at timestamptz not null default now()
);

-- Weekly review log: what the system got right/wrong and what it's adjusting
create table if not exists weekly_reviews (
    id bigint generated always as identity primary key,
    week_start date not null,
    week_end date not null,
    total_predictions integer not null,
    correct_predictions integer not null,
    accuracy_pct numeric not null,
    summary text not null,
    lessons jsonb not null,
    created_at timestamptz not null default now()
);

-- Chat log (rule-based Q&A, kept for "memory"/context)
create table if not exists chat_log (
    id bigint generated always as identity primary key,
    role text not null,                   -- 'user' | 'agent'
    message text not null,
    context jsonb,
    created_at timestamptz not null default now()
);

-- ===================================================================
-- Row Level Security: dashboard (anon key) can read everything and can
-- insert/update ONLY portfolio + chat_log (your direct actions).
-- Everything else (predictions, trades, reviews, weights) is written only
-- by the GitHub Actions jobs using the service_role key, which bypasses RLS.
-- ===================================================================
alter table portfolio enable row level security;
alter table planetary_log enable row level security;
alter table predictions enable row level security;
alter table rule_weights enable row level security;
alter table paper_account enable row level security;
alter table paper_trades enable row level security;
alter table weekly_reviews enable row level security;
alter table chat_log enable row level security;

create policy "public read portfolio" on portfolio for select using (true);
create policy "public write portfolio" on portfolio for insert with check (true);
create policy "public update portfolio" on portfolio for update using (true);
create policy "public delete portfolio" on portfolio for delete using (true);

create policy "public read planetary_log" on planetary_log for select using (true);
create policy "public read predictions" on predictions for select using (true);
create policy "public read rule_weights" on rule_weights for select using (true);
create policy "public read paper_account" on paper_account for select using (true);
create policy "public read paper_trades" on paper_trades for select using (true);
create policy "public read weekly_reviews" on weekly_reviews for select using (true);

create policy "public read chat_log" on chat_log for select using (true);
create policy "public write chat_log" on chat_log for insert with check (true);
