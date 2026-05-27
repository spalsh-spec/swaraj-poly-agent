"""signal_log.py — append every scanner signal to signals_log.csv.

One row per signal seen, regardless of whether it was traded.
Used for backtesting and signal quality analysis.

CSV columns:
    scanned_at, question, market_id, condition_id, token_id,
    H, regime, momentum, p_market, p_true,
    kelly_yes, kelly_no, best_kelly, side, volume, end_date

Usage:
    from swaraj_poly.signal_log import log_signals
    log_signals(signals)   # list[dict] from scan_markets()
"""
from __future__ import annotations
import csv, os, time, logging
from pathlib import Path

log = logging.getLogger("signal_log")

LOG_DIR  = Path(os.path.dirname(__file__)).parent / "dashboard"
LOG_PATH = LOG_DIR / "signals_log.csv"

COLUMNS = [
    "scanned_at", "question", "market_id", "condition_id", "token_id",
    "H", "regime", "momentum", "p_market", "p_true",
    "kelly_yes", "kelly_no", "best_kelly", "side",
    "volume", "end_date", "price_points",
]


def log_signals(signals: list[dict]) -> int:
    """Append signals to CSV. Returns number of rows written."""
    if not signals:
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_PATH.exists()

    try:
        with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            ts = int(time.time())
            for sig in signals:
                row = {col: sig.get(col, "") for col in COLUMNS}
                if not row.get("scanned_at"):
                    row["scanned_at"] = ts
                writer.writerow(row)
        log.info(f"[SIGNAL LOG] +{len(signals)} rows → {LOG_PATH}")
        return len(signals)
    except Exception as e:
        log.warning(f"[SIGNAL LOG] write failed: {e}")
        return 0


def tail_signals(n: int = 20) -> list[dict]:
    """Read last n rows from signals_log.csv. Returns list of dicts."""
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return rows[-n:]
    except Exception:
        return []


def signal_stats() -> dict:
    """Compute basic stats on logged signals: count, avg H, avg kelly."""
    if not LOG_PATH.exists():
        return {}
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return {}
        hs     = [float(r["H"]) for r in rows if r.get("H")]
        kellys = [float(r["best_kelly"]) for r in rows if r.get("best_kelly")]
        regimes = [r.get("regime","") for r in rows]
        return {
            "total_signals":    len(rows),
            "avg_H":            round(sum(hs) / len(hs), 4) if hs else 0,
            "max_H":            round(max(hs), 4) if hs else 0,
            "avg_kelly":        round(sum(kellys) / len(kellys), 4) if kellys else 0,
            "max_kelly":        round(max(kellys), 4) if kellys else 0,
            "persistent_count": regimes.count("PERSISTENT"),
            "log_path":         str(LOG_PATH),
        }
    except Exception as e:
        log.warning(f"[SIGNAL STATS] {e}")
        return {}
