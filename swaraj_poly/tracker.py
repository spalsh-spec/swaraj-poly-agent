"""tracker.py — persist state atomically; poll fills; update P&L.

P0 guardrail: write to .tmp then os.replace() — never corrupt on crash.
"""
from __future__ import annotations
import json, time, logging, os, tempfile
from . import config

log = logging.getLogger("tracker")
STATE_FILE = os.path.expanduser("~/.swaraj_poly_state.json")


def load_state() -> dict:
    """Load state from disk; return fresh skeleton on any error."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"state load error ({e}) — starting fresh")
    return {
        "positions": {},
        "open_orders": {},          # order_id → {token_id, side, size_usdc, ts}
        "condition_ids": [],        # P1: dedup — track condition_ids with open bets
        "trades": [],
        "daily_pnl": 0.0,
        "total_pnl": 0.0,
    }


def save_state(state: dict):
    """Atomic write: temp file → os.replace().  Never half-written on crash."""
    dir_ = os.path.dirname(STATE_FILE)
    os.makedirs(dir_ if dir_ else ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE_FILE) or ".",
                                prefix=".swaraj_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)   # atomic on POSIX / macOS
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record_trade(state: dict, trade: dict):
    """Append closed-trade record and accumulate PnL."""
    state["trades"].append({**trade, "ts": int(time.time())})
    state["daily_pnl"]  = round(state.get("daily_pnl", 0) + trade.get("pnl", 0), 4)
    state["total_pnl"]  = round(state.get("total_pnl", 0) + trade.get("pnl", 0), 4)
    save_state(state)


def reset_daily_pnl(state: dict):
    state["daily_pnl"] = 0.0
    save_state(state)


def print_summary(state: dict):
    pos = state.get("positions", {})
    log.info("── Tracker summary ──────────────────────────────")
    log.info(f"  Open positions : {len(pos)}")
    log.info(f"  Open orders    : {len(state.get('open_orders', {}))}")
    log.info(f"  Daily P&L      : ${state.get('daily_pnl', 0):.2f}")
    log.info(f"  Total P&L      : ${state.get('total_pnl', 0):.2f}")
    log.info(f"  Trades closed  : {len(state.get('trades', []))}")
