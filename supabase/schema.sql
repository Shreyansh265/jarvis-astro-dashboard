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

-- Postgres has no "create policy if not exists", so every policy below is
-- dropped-then-recreated -- makes the WHOLE file safe to paste and re-run
-- from scratch at any time, not just the tables added after your first run.
drop policy if exists "public read portfolio" on portfolio;
create policy "public read portfolio" on portfolio for select using (true);
drop policy if exists "public write portfolio" on portfolio;
create policy "public write portfolio" on portfolio for insert with check (true);
drop policy if exists "public update portfolio" on portfolio;
create policy "public update portfolio" on portfolio for update using (true);
drop policy if exists "public delete portfolio" on portfolio;
create policy "public delete portfolio" on portfolio for delete using (true);

drop policy if exists "public read planetary_log" on planetary_log;
create policy "public read planetary_log" on planetary_log for select using (true);
drop policy if exists "public read predictions" on predictions;
create policy "public read predictions" on predictions for select using (true);
drop policy if exists "public read rule_weights" on rule_weights;
create policy "public read rule_weights" on rule_weights for select using (true);
drop policy if exists "public read paper_account" on paper_account;
create policy "public read paper_account" on paper_account for select using (true);
drop policy if exists "public read paper_trades" on paper_trades;
create policy "public read paper_trades" on paper_trades for select using (true);
drop policy if exists "public read weekly_reviews" on weekly_reviews;
create policy "public read weekly_reviews" on weekly_reviews for select using (true);

drop policy if exists "public read chat_log" on chat_log;
create policy "public read chat_log" on chat_log for select using (true);
drop policy if exists "public write chat_log" on chat_log;
create policy "public write chat_log" on chat_log for insert with check (true);

-- ===================================================================
-- Graha epic additions (daily learning loop, stock-level picks, tabs)
-- Safe to re-run: every statement below is idempotent.
-- ===================================================================

-- Fix: predictions had no uniqueness guarantee, so any same-day re-run of
-- main_daily.py (e.g. a retry, or a manual + scheduled run landing on the
-- same UTC day) silently duplicated rows instead of updating them. De-dup
-- existing data BEFORE adding the index, or index creation fails on the
-- duplicate rows already present. Keep the reviewed copy if one exists
-- (don't throw away real review history), otherwise the newest row.
delete from predictions a using predictions b
where a.date = b.date and a.sector = b.sector
  and (a.reviewed, a.id) < (b.reviewed, b.id);

create unique index if not exists predictions_date_sector_uidx
  on predictions(date, sector);

-- Astro Stocks: individual stock picks within bullish/bearish sectors,
-- tracked from suggestion date until the user removes them from view.
-- Soft-delete only (is_active flag) -- daily_review.py / weekly_review.py
-- need full history to learn from even after a user stops watching a pick.
create table if not exists suggested_stocks (
    id bigint generated always as identity primary key,
    date_suggested date not null default current_date,
    sector text not null,
    ticker text not null,
    direction text not null,
    reasoning text not null,
    price_at_suggestion numeric,
    is_active boolean not null default true,
    removed_at timestamptz,
    created_at timestamptz not null default now()
);
alter table suggested_stocks enable row level security;
drop policy if exists "public read suggested_stocks" on suggested_stocks;
create policy "public read suggested_stocks" on suggested_stocks for select using (true);
-- No anon insert/update policy on purpose -- inserts are service-role only
-- (engine), and the only mutation the browser can make is via the narrow
-- RPC below, which flips exactly one flag and nothing else. A blanket
-- "anon can update" policy (like portfolio's) would let the browser corrupt
-- price_at_suggestion/reasoning, which the learning loop depends on.
create or replace function remove_suggested_stock(p_id bigint)
returns void
language sql
security definer
set search_path = public
as $$
  update suggested_stocks set is_active = false, removed_at = now() where id = p_id;
$$;
grant execute on function remove_suggested_stock(bigint) to anon;

-- Curated-watchlist daily price scan: powers "top gainers/losers" (Twelve
-- Data's free tier has no market-wide movers endpoint) and the "current
-- price" column on Astro Stocks. One row per ticker per day.
create table if not exists market_snapshot (
    id bigint generated always as identity primary key,
    date date not null default current_date,
    ticker text not null,
    sector text,
    price numeric not null,
    percent_change numeric,
    created_at timestamptz not null default now(),
    unique (date, ticker)
);
alter table market_snapshot enable row level security;
drop policy if exists "public read market_snapshot" on market_snapshot;
create policy "public read market_snapshot" on market_snapshot for select using (true);

-- Daily mark-to-market equity snapshot. paper_account.cash alone was never
-- a true equity figure once open positions exist -- especially now that
-- short positions exist, where the open liability isn't cash at all.
-- Sign convention (see paper_trader.py for the worked example): an open
-- LONG contributes +(qty*current_price) to positions_value; an open SHORT
-- contributes -(qty*current_price) (a liability, not an asset), because
-- opening a short already credited the sale proceeds to cash.
create table if not exists equity_history (
    id bigint generated always as identity primary key,
    date date not null unique,
    cash numeric not null,
    positions_value numeric not null,
    total_equity numeric not null,
    created_at timestamptz not null default now()
);
alter table equity_history enable row level security;
drop policy if exists "public read equity_history" on equity_history;
create policy "public read equity_history" on equity_history for select using (true);

-- ELI5 daily brief, generated from our own signals + price data only --
-- no third-party news source, no LLM.
create table if not exists daily_briefs (
    id bigint generated always as identity primary key,
    date date not null unique,
    brief_text text not null,
    created_at timestamptz not null default now()
);
alter table daily_briefs enable row level security;
drop policy if exists "public read daily_briefs" on daily_briefs;
create policy "public read daily_briefs" on daily_briefs for select using (true);

-- Long vs. short leg of a paper_trades position. `action` keeps meaning
-- open/close (BUY/SELL for a long, SHORT/COVER for the new short leg);
-- position_type is the independent long/short axis -- keeping these two
-- separate avoids overloading `action` with four ad-hoc string values.
alter table paper_trades add column if not exists position_type text not null default 'long' check (position_type in ('long','short'));
