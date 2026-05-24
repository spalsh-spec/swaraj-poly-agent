"""tracker.py — poll fills, update P&L, persist state to JSON."""
import json, time, logging, os
from . import config

log = logging.getLogger("tracker")
STATE_FILE = os.path.expanduser("~/.swaraj_poly_state.json")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"positions": {}, "trades": [], "daily_pnl": 0.0, "total_pnl": 0.0}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def record_trade(state: dict, trade: dict):
    """Append a closed-trade record and accumulate PnL."""
    state["trades"].append({**trade, "ts": int(time.time())})
    state["daily_pnl"]  = round(state.get("daily_pnl", 0) + trade.get("pnl", 0), 4)
    state["total_pnl"]  = round(state.get("total_pnl", 0) + trade.get("pnl", 0), 4)
    save_state(state)


def reset_daily_pnl(state: dict):
    state["daily_pnl"] = 0.0
    save_state(state)


def print_summary(state: dict):
    pos = state.get("positions", {})
    log.info(f"── Tracker summary ──────────────────────────────")
    log.info(f"  Open positions : {len(pos)}")
    log.info(f"  Daily P&L      : ${state.get('daily_pnl', 0):.2f}")
    log.info(f"  Total P&L      : ${state.get('total_pnl', 0):.2f}")
    log.info(f"  Trades closed  : {len(state.get('trades', []))}")
