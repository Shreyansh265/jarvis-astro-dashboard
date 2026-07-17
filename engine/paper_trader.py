"""
Simulated $20,000 paper trading account. No real money, no real broker --
pure logic + Supabase state. Runs daily via GitHub Actions.

Strategy (simple, transparent, and stated up front so it's auditable):
  - BUY the sector ETF when possibility_indicator >= BUY_THRESHOLD and direction == bullish,
    sizing the position as an equal-weight slice of currently available cash
    (capped at MAX_POSITIONS open at once).
  - SELL an open position when EITHER:
      a) the engine's signal for that sector has flipped bearish, OR
      b) a stop-loss (-8%) or take-profit (+15%) is hit, OR
      c) it's been held longer than MAX_HOLD_DAYS with no strong signal either way.
  - Every trade logs the exact possibility_indicator and reasons that triggered it.
"""
from datetime import datetime, date, timedelta
import supabase_client as db
import data_fetch

BUY_THRESHOLD = 65
MAX_POSITIONS = 5
STOP_LOSS_PCT = -8.0
TAKE_PROFIT_PCT = 15.0
MAX_HOLD_DAYS = 20


def _get_open_positions():
    trades = db.select("paper_trades", {"order": "created_at.asc"})
    open_pos = {}
    for t in trades:
        if t["action"] == "BUY":
            open_pos[t["id"]] = t
        elif t["action"] == "SELL" and t.get("linked_buy_trade_id") in open_pos:
            del open_pos[t["linked_buy_trade_id"]]
    return open_pos


def _get_cash():
    acct = db.select("paper_account", {"limit": 1})
    return acct[0]["cash"], acct[0]["id"]


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
        try:
            quote = data_fetch.get_quote(ticker)
        except Exception as e:
            log.append(f"Could not fetch price for {ticker}: {e}")
            continue
        current_price = quote["price"]
        pct_change = round((current_price - pos["price"]) / pos["price"] * 100, 2)
        held_days = (date.today() - datetime.strptime(pos["trade_date"], "%Y-%m-%d").date()).days

        sector_signal = signals.get(sector, {})
        signal_flipped = sector_signal.get("direction") == "bearish"

        reason = None
        if pct_change <= STOP_LOSS_PCT:
            reason = f"Stop-loss triggered ({pct_change}%)"
        elif pct_change >= TAKE_PROFIT_PCT:
            reason = f"Take-profit triggered ({pct_change}%)"
        elif signal_flipped:
            reason = f"Astrological signal for {sector} flipped bearish (possibility {sector_signal.get('possibility_indicator')})"
        elif held_days >= MAX_HOLD_DAYS:
            reason = f"Max hold period ({MAX_HOLD_DAYS} days) reached with no strong signal"

        if reason:
            proceeds = current_price * pos["quantity"]
            pnl = round(proceeds - (pos["price"] * pos["quantity"]), 2)
            db.insert("paper_trades", {
                "ticker": ticker, "sector": sector, "action": "SELL",
                "quantity": pos["quantity"], "price": current_price,
                "reasoning": reason, "trade_date": today,
                "linked_buy_trade_id": buy_id, "pnl": pnl, "pnl_pct": pct_change,
            })
            cash += proceeds
            log.append(f"SELL {ticker}: {reason}. P&L ${pnl} ({pct_change}%)")

    # 2) Look for new entries
    slots_free = MAX_POSITIONS - len(_get_open_positions())
    if slots_free > 0 and cash > 500:
        candidates = sorted(
            [(sector, s) for sector, s in signals.items()
             if s["direction"] == "bullish" and s["possibility_indicator"] >= BUY_THRESHOLD],
            key=lambda x: -x[1]["possibility_indicator"]
        )[:slots_free]

        position_size = cash / max(1, len(candidates)) if candidates else 0
        for sector, sig in candidates:
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
            cost = qty * quote["price"]
            reasoning = ("Buying on bullish astrological signal (possibility "
                         f"{sig['possibility_indicator']}/100): " + "; ".join(sig["reasons"][:3]))
            db.insert("paper_trades", {
                "ticker": ticker, "sector": sector, "action": "BUY",
                "quantity": qty, "price": quote["price"], "reasoning": reasoning,
                "possibility_indicator": sig["possibility_indicator"], "trade_date": today,
            })
            cash -= cost
            log.append(f"BUY {qty} {ticker} @ ${quote['price']} — {reasoning}")

    db.update("paper_account", {"id": f"eq.{acct_id}"}, {"cash": round(cash, 2)})
    return log


if __name__ == "__main__":
    import signals as sig_mod
    out = sig_mod.generate_signals()
    result = run_daily_paper_trading(out["sectors"])
    for line in result:
        print(line)
