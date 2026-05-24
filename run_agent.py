#!/usr/bin/env python3
"""run_agent.py — entry point.

Usage:
    python run_agent.py                  # live mode (reads .env)
    DRY_RUN=True python run_agent.py     # override to dry-run
"""
import asyncio, sys, os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from swaraj_poly.agent import SwarajPolyAgent
from swaraj_poly import config

if __name__ == "__main__":
    if not config.POLY_PRIVATE_KEY or config.POLY_PRIVATE_KEY.startswith("0x_YOUR"):
        print("❌  Set POLY_PRIVATE_KEY in .env before running.")
        print("   Copy .env.template → .env and fill in credentials.")
        sys.exit(1)

    agent = SwarajPolyAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n⛔ Agent stopped by user.")
