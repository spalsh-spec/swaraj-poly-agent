# Swaraj Poly Agent — Deployment Guide

## Prerequisites

- Python 3.11+
- pip
- A Polymarket account with CLOB API access
- (Optional for live trading) MATIC in your Polygon wallet for gas

---

## Step 1 — Install dependencies

```bash
cd /Users/sparshsharma/Projects/swaraj-poly-agent
pip install -r requirements.txt

# Verify setup
python setup_check.py
```

---

## Step 2 — Configure .env

```bash
cp .env.example .env
nano .env   # or use your editor
```

Minimum for dry-run (no credentials needed):
```
DRY_RUN=True
BANKROLL_USDC=100.0
```

For live trading, also set:
```
POLY_PRIVATE_KEY=0x...
POLY_API_KEY=...
POLY_API_SECRET=...
POLY_API_PASSPHRASE=...
DRY_RUN=False
```

### Getting Polymarket credentials
1. Go to https://polymarket.com → Connect wallet
2. Account → API keys → Generate API credentials
3. Export private key from your Polygon wallet (MetaMask or similar)
4. Fund wallet with MATIC (minimum 0.05 MATIC for gas — ~$0.03)

---

## Step 3 — Run dry-run (always do this first)

```bash
DRY_RUN=True python run_agent.py
```

Expected output:
```
🔬  DRY_RUN mode — no orders will be placed.
Signals found: 8
[DRY RUN] YES 0.30sh @ 0.4200 | token=...
```

If you see 0 signals: check internet connection, wait 15 min (markets may be quiet).

---

## Step 4 — Launch dashboard

In a separate terminal:
```bash
python dashboard/server.py
# Open: http://localhost:8765
```

---

## Step 5 — Install as macOS background service (optional)

The agent runs continuously (scan every 15 min), survives terminal close, restarts on crash.

```bash
# Edit plists to match your Python path (run: which python3)
nano com.swaraj.poly-agent.plist   # update ProgramArguments path

cp com.swaraj.poly-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.swaraj.poly-agent.plist

# Check it's running:
launchctl list | grep swaraj
tail -f /tmp/swaraj-poly-agent.log
```

Daily digest at 07:00:
```bash
cp com.swaraj.digest.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.swaraj.digest.plist

# Test immediately:
launchctl start com.swaraj.digest
# Check: cat dashboard/digest_YYYYMMDD.html
```

---

## Step 6 — Go live checklist

Before setting DRY_RUN=False:

- [ ] `python run_agent.py` ran successfully in DRY_RUN mode
- [ ] 8+ signals found in at least 3 consecutive dry runs
- [ ] .env has all 4 Polymarket credentials
- [ ] MATIC balance >= 0.05 (agent will abort if lower)
- [ ] BANKROLL_USDC set to amount you can afford to lose
- [ ] MAX_DAILY_LOSS set (default $20)
- [ ] MAX_POSITIONS set (default 5)
- [ ] You understand: this is automated trading. There is real financial risk.

```bash
# Final check before live:
DRY_RUN=False python -c "from swaraj_poly.agent import _check_matic_balance; _check_matic_balance()"
# Should print: [MATIC CHECK] wallet=0x... balance=X.XXXX MATIC

# Go live:
DRY_RUN=False python run_agent.py
```

---

## Risk parameters (defaults)

| Parameter | Default | Meaning |
|---|---|---|
| BANKROLL_USDC | 100 | Total capital available |
| MAX_SINGLE_BET | 0.10 | Max 10% of bankroll per position |
| MAX_EXPOSURE | 0.25 | Max 25% of bankroll deployed at once |
| MAX_DAILY_LOSS | 20 | Agent pauses if daily P&L < -$20 |
| MAX_POSITIONS | 5 | Max 5 concurrent open positions |
| MIN_HURST | 0.55 | Only trade H > 0.55 markets |
| MIN_KELLY | 0.02 | Min kelly fraction to trade |
| MAX_HOLD_DAYS | 7 | Auto-close positions after 7 days |

---

## Current git state

```
swaraj-poly-agent main @ 6d23137
  - scanner.py v1.2 (clobTokenIds parse fix — 8+ signals per scan)
  - executor.py (CLOB order placement, fill verification, exponential backoff)
  - tracker.py (atomic P&L state, crash-safe)
  - agent.py (full loop: scan→signal→risk→execute→close→track)
  - signal_log.py (CSV logging of all signals for backtesting)
  - digest.py (daily HTML email report)
  - dashboard/server.py (localhost:8765 live view)
  - 7 architectural decision records in docs/DECISIONS.md
```
