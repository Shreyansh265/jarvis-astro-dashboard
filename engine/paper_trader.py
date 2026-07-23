"""
Simulated $20,000 paper trading account. No real money, no real broker --
pure logic + Supabase state. Runs daily via GitHub Actions. Target: track
toward roughly 15%/month -- an aspirational goal surfaced on the dashboard
as a progress metric, not a guarantee (simulated money only; the strategy
below isn't tuned to force that number, just to actually use every
high-confidence signal Graha generates instead of sitting idle).

Strategy (simple, transparent, and stated up front so it's auditable):
  - OPEN A LONG (BUY) on a sector ETF when direction == bullish and
    possibility_indicator >= BUY_THRESHOLD.
  - OPEN A SHORT on a sector ETF when direction == bearish and
    possibility_indicator >= SHORT_THRESHOLD. Added because a long-only bot
    sits in 100% cash on any day where every strong signal happens to be
    bearish -- observed live: an 11-bearish/0-bullish real trading day left
    a long-only version of this bot with zero trades despite several
    80-95%-confidence signals it had no way to act on. Shorting lets it act
    on high-confidence calls in either direction. The confidence floor
    stays in place on BOTH sides -- this isn't "trade regardless of
    confidence to force daily activity," it's "don't ignore the bearish
    half of your own convictions."
  - Both directions rank by confidence and fill up to MAX_POSITIONS total
    (long + short combined) as cash allows.
  - CLOSE a position (SELL for a long, COVER for a short) when EITHER:
      a) the engine's signal for that sector has flipped away from the
         direction that opened it, OR
      b) a stop-loss or take-profit is hit (mirrored by position_type --
         see _exit_reason below), OR
      c) it's been held longer than MAX_HOLD_DAYS with no strong signal.
  - Every trade logs the exact possibility_indicator and reasons that
    triggered it.

SHORT ledger convention -- read this before touching the money math:
  Opening a short credits `cash` with the sale proceeds (qty*entry_price)
  -- real simulated cash the account now holds -- but it also books a
  LIABILITY: the obligation to buy the shares back later. So an open
  short's mark-to-market contribution to total equity is NEGATIVE
  (-(qty*current_price)), not positive like a long (see
  _record_equity_snapshot). Worked example, hand-verified:
    Short 10 shares @ $50  -> cash += $500
    Price rises to $54 (+8%, stop-loss triggers) -> cover: cash -= $540
    Net cash effect: -$40
    pnl = (entry_price - current_price) * qty = (50 - 54) * 10 = -$40
  Matches: the account is down exactly $40, which is also exactly what
  equity_history should show relative to the prior snapshot if nothing
  else happened that day.
"""
from datetime import datetime, date
import supabase_client as db
import data_fetch

BUY_THRESHOLD = 65
SHORT_THRESHOLD = 65
MAX_POSITIONS = 5
STOP_LOSS_PCT = 8.0     # magnitude only; direction depends on position_type
TAKE_PROFIT_PCT = 15.0  # magnitude only; direction depends on position_type
MAX_HOLD_DAYS = 20


def _get_open_positions():
    trades = db.select("paper_trades", {"order": "created_at.asc"})
    open_pos = {}
    for t in trades:
        if t["action"] in ("BUY", "SHORT"):
            open_pos[t["id"]] = t
        elif t["action"] in ("SELL", "COVER") and t.get("linked_buy_trade_id") in open_pos:
            del open_pos[t["linked_buy_trade_id"]]
    return open_pos


def _get_cash():
    acct = db.select("paper_account", {"limit": 1})
    return acct[0]["cash"], acct[0]["id"]


def _pct_change(entry_price, current_price):
    """Always (current-entry)/entry -- positive means price rose, regardless
    of position_type. Callers interpret the sign per-direction (see
    _exit_reason); this function stays a literal, unambiguous price move."""
    return round((current_price - entry_price) / entry_price * 100, 2)


def _exit_reason(position_type, pct_change, sector_signal, held_days):
    if position_type == "long":
        if pct_change <= -STOP_LOSS_PCT:
            return f"Stop-loss triggered ({pct_change}%)"
        if pct_change >= TAKE_PROFIT_PCT:
            return f"Take-profit triggered ({pct_change}%)"
        if sector_signal.get("direction") == "bearish":
            return f"Astrological signal flipped bearish (possibility {sector_signal.get('possibility_indicator')})"
    else:  # short
        if pct_change >= STOP_LOSS_PCT:
            return f"Stop-loss triggered (price rose {pct_change}%)"
        if pct_change <= -TAKE_PROFIT_PCT:
            return f"Take-profit triggered (price fell {pct_change}%)"
        if sector_signal.get("direction") == "bullish":
            return f"Astrological signal flipped bullish (possibility {sector_signal.get('possibility_indicator')})"
    if held_days >= MAX_HOLD_DAYS:
        return f"Max hold period ({MAX_HOLD_DAYS} days) reached with no strong signal either way"
    return None


def run_daily_paper_trading(signals: dict):
    """signals = output of signals.generate_signals()['sectors']"""
    from rulerships import SECTOR_TICKERS

    cash, acct_id = _get_cash()
    open_positions = _get_open_positions()
    today = date.today().isoformat()
    log = []

    # 1) Check exits on open positions first
    for buy_id, pos in list(open_positions.items()):
        ticker = pos["ticker"]
        sector = pos["sector"]
        position_type = pos.get("position_type", "long")
        try:
            quote = data_fetch.get_quote(ticker)
        except Exception as e:
            log.append(f"Could not fetch price for {ticker}: {e}")
            continue
        current_price = quote["price"]
        pct_change = _pct_change(pos["price"], current_price)
        held_days = (date.today() - datetime.strptime(pos["trade_date"], "%Y-%m-%d").date()).days
        sector_signal = signals.get(sector, {})

        reason = _exit_reason(position_type, pct_change, sector_signal, held_days)
        if not reason:
            continue

        if position_type == "long":
            proceeds = current_price * pos["quantity"]
            pnl = round(proceeds - (pos["price"] * pos["quantity"]), 2)
            cash += proceeds
            close_action = "SELL"
        else:
            cost_to_cover = current_price * pos["quantity"]
            pnl = round((pos["price"] - current_price) * pos["quantity"], 2)
            cash -= cost_to_cover
            close_action = "COVER"

        db.insert("paper_trades", {
            "ticker": ticker, "sector": sector, "action": close_action,
            "position_type": position_type, "quantity": pos["quantity"], "price": current_price,
            "reasoning": reason, "trade_date": today,
            "linked_buy_trade_id": buy_id, "pnl": pnl, "pnl_pct": pct_change,
        })
        log.append(f"{close_action} {ticker} ({position_type}): {reason}. P&L ${pnl} (price move {pct_change}%)")

    # 2) Look for new entries -- rank bullish (long) and bearish (short)
    #    candidates together by confidence, fill remaining slots either way.
    open_positions = _get_open_positions()
    slots_free = MAX_POSITIONS - len(open_positions)
    if slots_free > 0 and cash > 500:
        long_candidates = [(sector, s, "long") for sector, s in signals.items()
                           if s["direction"] == "bullish" and s["possibility_indicator"] >= BUY_THRESHOLD]
        short_candidates = [(sector, s, "short") for sector, s in signals.items()
                            if s["direction"] == "bearish" and s["possibility_indicator"] >= SHORT_THRESHOLD]
        candidates = sorted(long_candidates + short_candidates,
                             key=lambda x: -x[1]["possibility_indicator"])[:slots_free]

        position_size = cash / max(1, len(candidates)) if candidates else 0
        for sector, sig, position_type in candidates:
            ticker = SECTOR_TICKERS.get(sector)
            if not ticker:
                continue
            try:
                quote = data_fetch.get_quote(ticker)
            except Exception as e:
                log.append(f"Could not fetch price for {ticker}: {e}")
                continue
            qty = round(position_size / quote["price"], 4)
            if qty <= 0:
                continue

            entry_action = "BUY" if position_type == "long" else "SHORT"
            verb = "Buying" if position_type == "long" else "Shorting"
            reasoning = (f"{verb} on {sig['direction']} astrological signal (possibility "
                         f"{sig['possibility_indicator']}/100): " + "; ".join(sig["reasons"][:3]))
            db.insert("paper_trades", {
                "ticker": ticker, "sector": sector, "action": entry_action,
                "position_type": position_type, "quantity": qty, "price": quote["price"],
                "reasoning": reasoning, "possibility_indicator": sig["possibility_indicator"],
                "trade_date": today,
            })
            if position_type == "long":
                cash -= qty * quote["price"]
            else:
                cash += qty * quote["price"]  # short-sale proceeds
            log.append(f"{entry_action} {qty} {ticker} @ ${quote['price']} — {reasoning}")

    db.update("paper_account", {"id": f"eq.{acct_id}"}, {"cash": round(cash, 2)})
    _record_equity_snapshot(cash, today)
    return log


def _record_equity_snapshot(cash: float, today: str):
    """Marks every open position to its current price. Longs are an asset
    (+); shorts are a liability (-) -- see module docstring for the sign
    convention and worked example."""
    positions_value = 0.0
    for pos in _get_open_positions().values():
        try:
            quote = data_fetch.get_quote(pos["ticker"])
        except Exception:
            continue
        market_value = quote["price"] * pos["quantity"]
        if pos.get("position_type", "long") == "long":
            positions_value += market_value
        else:
            positions_value -= market_value

    total_equity = round(cash + positions_value, 2)
    db.upsert("equity_history", {
        "date": today, "cash": round(cash, 2),
        "positions_value": round(positions_value, 2), "total_equity": total_equity,
    }, on_conflict="date")


if __name__ == "__main__":
    import signals as sig_mod
    out = sig_mod.generate_signals()
    result = run_daily_paper_trading(out["sectors"])
    for line in result:
        print(line)
