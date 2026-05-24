"""config.py — load all settings from .env with safe defaults."""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Polymarket credentials ───────────────────────────────────────────────────
POLY_PRIVATE_KEY   = os.getenv("POLY_PRIVATE_KEY", "")
POLY_API_KEY       = os.getenv("POLY_API_KEY", "")
POLY_API_SECRET    = os.getenv("POLY_API_SECRET", "")
POLY_API_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE", "")
POLY_CHAIN_ID      = int(os.getenv("POLY_CHAIN_ID", "137"))

# ── Risk parameters ──────────────────────────────────────────────────────────
BANKROLL_USDC   = float(os.getenv("BANKROLL_USDC", "100.0"))
MAX_EXPOSURE    = float(os.getenv("MAX_EXPOSURE", "0.25"))
MAX_SINGLE_BET  = float(os.getenv("MAX_SINGLE_BET", "0.10"))
MAX_DAILY_LOSS  = float(os.getenv("MAX_DAILY_LOSS", "20.0"))
MAX_POSITIONS   = int(os.getenv("MAX_POSITIONS", "5"))

# ── Signal thresholds ────────────────────────────────────────────────────────
MIN_HURST  = float(os.getenv("MIN_HURST", "0.55"))
MIN_KELLY  = float(os.getenv("MIN_KELLY", "0.005"))
MIN_VOLUME = float(os.getenv("MIN_VOLUME", "5000"))

# ── Timing ───────────────────────────────────────────────────────────────────
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "900"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# ── Safety ───────────────────────────────────────────────────────────────────
DRY_RUN = os.getenv("DRY_RUN", "True").strip().lower() in ("true", "1", "yes")

# ── API endpoints ────────────────────────────────────────────────────────────
GAMMA_API   = "https://gamma-api.polymarket.com"
CLOB_HOST   = "https://clob.polymarket.com"
