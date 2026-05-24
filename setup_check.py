#!/usr/bin/env python3
"""
setup_check.py — pre-flight verification before running the agent.
Run this once after filling in .env to confirm everything is wired.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

print("── swaraj-poly-agent pre-flight check ─────────────────")

# 1. Imports
try:
    from swaraj_poly import config
    print("✅ config loaded")
except Exception as e:
    print(f"❌ config import failed: {e}"); sys.exit(1)

# 2. Key present
if not config.POLY_PRIVATE_KEY or config.POLY_PRIVATE_KEY.startswith("0x_YOUR"):
    print("❌ POLY_PRIVATE_KEY not set in .env")
    print("   → Export from MetaMask: Account Details → Export Private Key")
else:
    print(f"✅ POLY_PRIVATE_KEY set ({config.POLY_PRIVATE_KEY[:6]}…)")

# 3. API creds
if not config.POLY_API_KEY:
    print("⚠️  POLY_API_KEY empty — needed for order placement")
    print("   → https://polymarket.com/settings/api-keys → Create API Key")
else:
    print("✅ POLY_API_KEY set")

# 4. DRY_RUN
if config.DRY_RUN:
    print("✅ DRY_RUN=True (safe mode — no real orders)")
else:
    print("🔴 DRY_RUN=False — LIVE TRADING ENABLED")

# 5. Risk params
print(f"✅ Bankroll: ${config.BANKROLL_USDC:.2f} | MaxBet: {config.MAX_SINGLE_BET*100:.0f}% | DailyLoss: ${config.MAX_DAILY_LOSS}")

# 6. Quick signal test (no network)
try:
    from swaraj_poly.signal import evaluate
    import random; random.seed(42)
    fake_prices = [0.5 + random.gauss(0, 0.05) for _ in range(60)]
    fake_prices = [max(0.01, min(0.99, p)) for p in fake_prices]
    sig = evaluate(fake_prices, fake_prices[-1])
    print(f"✅ Signal engine OK: H={sig['H']} regime={sig['regime']} kelly={sig['best_kelly']}")
except Exception as e:
    print(f"❌ Signal engine error: {e}")

# 7. aiohttp
try:
    import aiohttp
    print(f"✅ aiohttp {aiohttp.__version__}")
except ImportError:
    print("❌ aiohttp missing — run: pip install aiohttp --break-system-packages")

print("────────────────────────────────────────────────────────")
print()
if config.DRY_RUN:
    print("Ready to run in DRY_RUN mode:")
    print("  python run_agent.py")
    print()
    print("Watch the dashboard:")
    print("  open dashboard/live.html")
else:
    print("⚠️  LIVE MODE — double-check all settings before running!")
