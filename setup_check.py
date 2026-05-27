#!/usr/bin/env python3
"""setup_check.py — pre-flight verification for swaraj-poly-agent.

Run once after setting up .env:
    python setup_check.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

PASS, FAIL, WARN = "✅", "❌", "⚠️ "
errors = 0

def ok(msg):  print(f"{PASS} {msg}")
def fail(msg): global errors; errors += 1; print(f"{FAIL} {msg}")
def warn(msg): print(f"{WARN} {msg}")

print("── swaraj-poly-agent pre-flight check ─────────────────")

# 1. Core imports
try:
    from swaraj_poly import config
    ok("config loaded")
except Exception as e:
    fail(f"config import: {e}"); sys.exit(1)

try:
    from swaraj_poly.scanner   import scan_markets; ok("scanner imported")
    from swaraj_poly.executor  import Executor;     ok("executor imported")
    from swaraj_poly.tracker   import load_state;   ok("tracker imported")
    from swaraj_poly.risk      import RiskManager;  ok("risk manager imported")
    from swaraj_poly.signal_log import log_signals, signal_stats; ok("signal_log imported")
    from swaraj_poly.digest    import send_digest;  ok("digest imported")
    from swaraj_poly.notify    import notify_startup; ok("notify imported")
    from swaraj_poly.agent     import SwarajPolyAgent; ok("agent imported")
except Exception as e:
    fail(f"module import: {e}")

# 2. Signal engine
try:
    from swaraj_poly.signal import evaluate
    import random; random.seed(42)
    prices = [max(0.01, min(0.99, 0.5 + random.gauss(0, 0.05))) for _ in range(80)]
    sig = evaluate(prices, prices[-1])
    ok(f"signal engine: H={sig['H']:.3f} regime={sig['regime']} kelly={sig['best_kelly']:.3f}")
except Exception as e:
    fail(f"signal engine: {e}")

# 3. DRY_RUN mode
if config.DRY_RUN:
    ok(f"DRY_RUN=True (safe mode — no real orders)")
else:
    print(f"🔴 DRY_RUN=False — LIVE TRADING ENABLED")

# 4. Credentials (only required for live mode)
if not config.DRY_RUN:
    if not config.POLY_PRIVATE_KEY or config.POLY_PRIVATE_KEY.startswith("0x_YOUR"):
        fail("POLY_PRIVATE_KEY not set — required for live trading")
    else:
        ok(f"POLY_PRIVATE_KEY set ({config.POLY_PRIVATE_KEY[:6]}…)")
    if not config.POLY_API_KEY:
        fail("POLY_API_KEY missing")
    else:
        ok("POLY_API_KEY set")
else:
    warn("Credential check skipped (DRY_RUN=True)")

# 5. Risk params
ok(f"Bankroll: ${config.BANKROLL_USDC:.2f} | MaxBet: {config.MAX_SINGLE_BET*100:.0f}% | "
   f"MaxPositions: {config.MAX_POSITIONS} | DailyLoss cap: ${config.MAX_DAILY_LOSS}")

# 6. aiohttp
try:
    import aiohttp; ok(f"aiohttp {aiohttp.__version__}")
except ImportError:
    fail("aiohttp missing — run: pip install aiohttp")

# 7. Telegram (optional)
tok = os.getenv("TELEGRAM_BOT_TOKEN","")
cid = os.getenv("TELEGRAM_CHAT_ID","")
if tok and cid:
    ok(f"Telegram configured (chat_id={cid[:8]}…)")
else:
    warn("TELEGRAM_BOT_TOKEN/CHAT_ID not set — notifications disabled (optional)")

# 8. Digest email (optional)
if os.getenv("DIGEST_EMAIL_TO",""):
    ok(f"Digest email → {os.getenv('DIGEST_EMAIL_TO')}")
else:
    warn("DIGEST_EMAIL_TO not set — digest will write HTML file instead (optional)")

# 9. Dashboard
from pathlib import Path
dashboard = Path("dashboard/server.py")
if dashboard.exists():
    ok("Dashboard server: python dashboard/server.py → http://localhost:8765")
else:
    warn("dashboard/server.py missing")

# 10. Backtest
backtest = Path("backtest.py")
if backtest.exists():
    ok("Backtest: python backtest.py (after first scan collects signals)")
else:
    warn("backtest.py missing")

print("────────────────────────────────────────────────────────")
if errors:
    print(f"\n{errors} error(s) found. Fix above before running the agent.")
    sys.exit(1)
else:
    print(f"\nAll checks passed.")
    if config.DRY_RUN:
        print("\nStart agent:         python run_agent.py")
        print("Watch dashboard:     python dashboard/server.py")
        print("Run backtest later:  python backtest.py")
    else:
        print("\n⚠️  LIVE MODE — verify risk params above, then: python run_agent.py")
