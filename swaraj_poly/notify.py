"""notify.py — Telegram notifications for Swaraj signal events.

Sends a message when:
  - High-confidence signal found (H > NOTIFY_H_THRESHOLD, kelly > NOTIFY_KELLY_THRESHOLD)
  - Order filled (live mode)
  - Daily loss circuit breaker trips
  - Agent starts or stops

Config (.env):
    TELEGRAM_BOT_TOKEN  = 12345678:AABBcc...   (from @BotFather)
    TELEGRAM_CHAT_ID    = -1001234567890       (group) or 123456789 (personal)
    NOTIFY_H_THRESHOLD  = 0.65                 (only notify high-H signals)
    NOTIFY_KELLY_THRESHOLD = 0.10              (only notify meaningful kelly)

Setup:
    1. Open Telegram → search @BotFather → /newbot
    2. Copy the token
    3. Add bot to your channel/group, or message it directly
    4. Get your chat_id: https://api.telegram.org/bot<TOKEN>/getUpdates

If TELEGRAM_BOT_TOKEN is empty, all calls are silent no-ops.
"""
from __future__ import annotations
import os, urllib.request, urllib.parse, json, logging, time

log = logging.getLogger("notify")

BOT_TOKEN         = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID           = os.getenv("TELEGRAM_CHAT_ID", "")
NOTIFY_H          = float(os.getenv("NOTIFY_H_THRESHOLD", "0.65"))
NOTIFY_KELLY      = float(os.getenv("NOTIFY_KELLY_THRESHOLD", "0.10"))

_LAST_SEND: float = 0
_MIN_INTERVAL = 5   # seconds between messages (rate-limit guard)


def _send(text: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    global _LAST_SEND
    if not BOT_TOKEN or not CHAT_ID:
        return False
    # Rate limit
    now = time.time()
    if now - _LAST_SEND < _MIN_INTERVAL:
        return False
    _LAST_SEND = now

    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            ok = json.loads(resp.read()).get("ok", False)
            if not ok:
                log.warning("[NOTIFY] Telegram API returned ok=false")
            return ok
    except Exception as e:
        log.debug(f"[NOTIFY] send failed: {e}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def notify_signal(sig: dict):
    """Notify on high-confidence signal."""
    h     = float(sig.get("H", 0))
    kelly = float(sig.get("best_kelly", 0))
    if h < NOTIFY_H or kelly < NOTIFY_KELLY:
        return   # below notification threshold

    side  = sig.get("side", "")
    emoji = "🟢" if side == "YES" else "🔴"
    q     = (sig.get("question") or "")[:80]
    dry   = " <i>[DRY RUN]</i>" if os.getenv("DRY_RUN","True").lower() in ("true","1") else ""
    text  = (
        f"⚡ <b>Swaraj Signal</b>{dry}\n\n"
        f"{emoji} <b>{side}</b> | H={h:.3f} | Kelly={kelly:.3f}\n"
        f"Market: {sig.get('p_market',0):.3f} → True P: {sig.get('p_true',0):.3f}\n"
        f"Regime: {sig.get('regime','')}\n\n"
        f"<i>{q}</i>"
    )
    _send(text)


def notify_fill(sig: dict, bet_size: float, order_id: str):
    """Notify on successful order fill."""
    side  = sig.get("side", "")
    emoji = "✅"
    dry   = os.getenv("DRY_RUN","True").lower() in ("true","1")
    mode  = " [DRY RUN]" if dry else " [LIVE]"
    text  = (
        f"{emoji} <b>Order{mode}</b>\n\n"
        f"{side} ${bet_size:.2f} USDC\n"
        f"Order: <code>{order_id[:16]}…</code>\n"
        f"H={sig.get('H',0):.3f} kelly={sig.get('best_kelly',0):.3f}\n\n"
        f"<i>{(sig.get('question') or '')[:80]}</i>"
    )
    _send(text)


def notify_circuit_breaker(daily_pnl: float):
    """Notify when daily loss limit trips."""
    text = (
        f"🛑 <b>Swaraj — Circuit Breaker</b>\n\n"
        f"Daily P&L: <b>${daily_pnl:+.2f}</b>\n"
        f"Agent paused. Restart tomorrow."
    )
    _send(text)


def notify_startup(dry_run: bool, bankroll: float):
    """Notify on agent start."""
    mode = "🔬 DRY RUN" if dry_run else "💰 LIVE"
    text = (
        f"⚡ <b>Swaraj started</b>\n"
        f"Mode: {mode}\n"
        f"Bankroll: ${bankroll:.2f} USDC"
    )
    _send(text)


def notify_close(pos: dict, exit_price: float, pnl: float, reason: str):
    """Notify on position close."""
    emoji = "📈" if pnl >= 0 else "📉"
    text  = (
        f"{emoji} <b>Position Closed</b>\n\n"
        f"P&L: <b>${pnl:+.4f}</b> | reason={reason}\n"
        f"Exit: {exit_price:.3f}\n\n"
        f"<i>{(pos.get('question') or '')[:80]}</i>"
    )
    _send(text)
