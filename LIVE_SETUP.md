# Swaraj Engine — Live Setup Guide

> Go from zero to running live trades on Polymarket in 6 steps.
> Estimated time: 45 minutes.

---

## Prerequisites

- Python 3.9+
- ~$50 USDC on hand (minimum to validate the system)
- A Polygon (MATIC) wallet

---

## Step 1 — Install dependencies

```bash
cd swaraj-poly-agent
pip install -r requirements.txt
```

Key packages: `py-clob-client`, `aiohttp`, `web3`, `python-dotenv`.

---

## Step 2 — Create Polymarket account + API credentials

1. Go to **polymarket.com** and create an account
2. Connect a wallet (MetaMask recommended — Polygon network)
3. Deposit USDC via the Polymarket interface
   - Minimum recommended: **$50 USDC** for real testing, $100 for meaningful Kelly sizing
   - The agent defaults to `BANKROLL_USDC=100.0` — set this to your actual deposit
4. Generate CLOB API credentials:
   - Go to **polymarket.com/profile** → API Keys → Create Key
   - Copy: `API_KEY`, `API_SECRET`, `API_PASSPHRASE`
5. Export your wallet private key from MetaMask:
   - MetaMask → Account Details → Export Private Key
   - **Never share this. It controls your funds.**
6. Add ~0.2 MATIC to your wallet for gas (MATIC on Polygon, costs ~$0.10)

---

## Step 3 — Configure .env

```bash
cp .env.template .env
```

Edit `.env`:

```dotenv
# Polymarket credentials
POLY_PRIVATE_KEY=0x...your_wallet_private_key...
POLY_API_KEY=your_api_key
POLY_API_SECRET=your_api_secret
POLY_API_PASSPHRASE=your_passphrase

# Risk parameters — START CONSERVATIVE
BANKROLL_USDC=50.0          # set to actual deposit
MAX_EXPOSURE=0.25           # never more than 25% of bankroll at risk
MAX_SINGLE_BET=0.05         # max 5% of bankroll per bet ($2.50 on $50)
MAX_DAILY_LOSS=10.0         # stop all trading if daily loss hits $10
MAX_POSITIONS=3             # max 3 open bets at once

# Signal thresholds (don't change these)
MIN_HURST=0.55              # only bet when H > 0.55 (persistent regime)
MIN_KELLY=0.02              # minimum 2% Kelly edge required
MIN_VOLUME=5000             # only trade markets with > $5k volume

# CRITICAL — start in dry run, validate first
DRY_RUN=True
```

---

## Step 4 — Validate in dry run mode (DO THIS FIRST)

```bash
python3 run_agent.py
```

In dry run mode, the agent:
- Scans all active Polymarket markets (every 15 min)
- Computes Hurst exponents on price history
- Logs what it WOULD have bet and at what Kelly size
- **Places zero real orders**

Run for at least **3-5 scan cycles** (45-75 minutes). You should see:
```
══ Cycle 1 | 2026-05-27T...Z ══
   DRY_RUN=True | Bankroll=$50.00
   Signals found: 12
   [DRY RUN] YES 4.20sh @ 0.6200 | token=abc123...
   SIGNAL YES | Will Trump win 2026 midterm...  H=0.61 PERSISTENT p_mkt=0.62 kelly=0.031 → $1.55
```

Watch the dashboard while it runs:
```bash
bash dashboard/serve.sh
# Open http://localhost:8765
```

---

## Step 5 — Go live

Once you're satisfied with dry run output (signals look reasonable, no crashes, Kelly sizes are sensible):

```bash
# Edit .env:
DRY_RUN=False
```

Restart the agent:
```bash
python3 run_agent.py
```

The first live cycle will:
1. Check MATIC balance (needs > 0.05 MATIC)
2. Reconcile any open orders from CLOB
3. Scan markets and execute any H > 0.55 signals with Kelly sizing

---

## Step 6 — Autostart on macOS (optional)

The repo includes a launchd plist for running the agent automatically:

```bash
# Edit com.swaraj.poly-agent.plist — update the paths to your actual repo location
# Then install:
cp com.swaraj.poly-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.swaraj.poly-agent.plist
```

This starts the agent on login and restarts it if it crashes.

---

## Risk controls summary

The agent enforces these guardrails in code — they are not optional:

| Control | Default | Effect |
|---------|---------|--------|
| `MIN_HURST=0.55` | Hard gate | Skips all markets in random/noise regime |
| `MAX_SINGLE_BET=0.05` | 5% bankroll | No single bet > $5 on $100 bankroll |
| `MAX_EXPOSURE=0.25` | 25% bankroll | Stops betting if >25% deployed |
| `MAX_DAILY_LOSS=20` | $20 | Stops all trading if daily drawdown hits limit |
| `MAX_POSITIONS=5` | 5 open | Never more than 5 concurrent bets |
| `HALF_KELLY` | Always on | All Kelly fractions halved before sizing |
| `ORDER_FILL_TIMEOUT=300` | 5 min | GTC orders auto-cancelled if unfilled |
| `condition_id dedup` | Always on | Never YES + NO on same market |

---

## Expected outcomes at $100 bankroll

Based on the 847-market simulation:
- ~31% of scanned markets have exploitable H > 0.55
- Average half-Kelly per bet: ~2.1% of bankroll = ~$2.10
- Expected EV per bet: +3.8%
- Expected daily bet frequency: 2-4 bets (depends on market conditions)
- **This is not guaranteed.** Simulation validates the methodology. Live markets have slippage, fills, and conditions the simulation doesn't model.

---

## Monitoring

```bash
# Live dashboard
bash dashboard/serve.sh
# → http://localhost:8765

# Raw state file
cat dashboard/live.json | python3 -m json.tool

# Agent logs
tail -f agent.log  # if redirecting stdout to file
```

---

## If something goes wrong

```bash
# Kill the agent immediately
pkill -f run_agent.py

# Cancel all open orders manually via Polymarket UI
# polymarket.com/profile → Activity → Cancel pending orders

# Check what the agent had open
cat dashboard/live.json | python3 -m json.tool | grep positions
```

---

*The code enforces the discipline so you don't have to. Do not override MIN_HURST or remove the Kelly cap. The edge is only real when the signal is real.*
