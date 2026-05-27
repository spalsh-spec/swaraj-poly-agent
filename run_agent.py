#!/usr/bin/env python3
"""run_agent.py — entry point.

Usage:
    python run_agent.py                  # live mode (reads .env)
    DRY_RUN=True python run_agent.py     # override to dry-run (no creds needed)
"""
import asyncio, sys, os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from swaraj_poly.agent import SwarajPolyAgent
from swaraj_poly import config

if __name__ == "__main__":
    # Credentials are only required for LIVE trading.
    # DRY_RUN mode simulates everything locally — no API calls to Polymarket.
    if not config.DRY_RUN:
        if not config.POLY_PRIVATE_KEY or config.POLY_PRIVATE_KEY.startswith("0x_YOUR"):
            print("❌  Set POLY_PRIVATE_KEY in .env before running in LIVE mode.")
            print("   Copy .env.template → .env and fill in credentials.")
            print("   To test without creds: DRY_RUN=True python run_agent.py")
            sys.exit(1)

    if config.DRY_RUN:
        print("🔬  DRY_RUN mode — no orders will be placed.")

    agent = SwarajPolyAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n⛔ Agent stopped by user.")
