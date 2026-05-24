# swaraj-poly-agent

**Autonomous Polymarket prediction trader using fractal signal analysis.**

Built on [swaraj-engine](https://github.com/spalsh-spec/swaraj-engine) — a mathematical framework
rooted in the same methodology as the Renaissance Medallion Fund:
detect persistent autocorrelation → size asymmetrically → execute.

---

## The Methodology (Jim Simons parallel)

Simons' core insight: markets aren't random — they exhibit **persistent autocorrelation**
that can be measured and traded. We measure this with the **Hurst exponent H**:

| H value | Regime | Interpretation |
|---------|--------|----------------|
| > 0.65  | TRENDING↗ | Strong momentum — bet with the drift |
| 0.55–0.65 | PERSISTENT | Mild momentum — half-Kelly |
| 0.45–0.55 | RANDOM | No edge — skip |
| < 0.45  | MEAN-REV↩ | Fade the extremes |

**Corrected Kelly for Polymarket** (asymmetric payoffs):

```python
# YES bet at price p_market:
b = (1 - p_market) / p_market   # actual payoff ratio
k = (p_true * b - (1 - p_true)) / b
bet_fraction = k / 2             # half-Kelly for variance control
```

**Fractal-adjusted probability** (from swaraj-engine):
```python
p_true = p_market + (momentum_signal * weight)  # TRENDING
p_true = p_market * 0.85 + 0.5 * 0.15          # MEAN-REV (pull to center)
```

---

## Architecture

```
swaraj-poly-agent/
├── run_agent.py          ← entry point: python run_agent.py
├── .env.template         ← copy to .env, fill in keys
├── swaraj_poly/
│   ├── config.py         ← env config + risk parameters
│   ├── signal.py         ← Hurst R/S + Kelly + momentum
│   ├── scanner.py        ← async market scanner (Gamma API + CLOB)
│   ├── executor.py       ← py-clob-client order placement
│   ├── risk.py           ← position limits + daily loss circuit-breaker
│   ├── tracker.py        ← state persistence (JSON)
│   └── agent.py          ← async event loop: scan→signal→risk→execute
└── dashboard/
    ├── live.html          ← self-refreshing P&L dashboard
    └── live.json          ← written by agent each cycle
```

---

## Quick Start

```bash
# 1. Clone & enter
cd ~/Projects/swaraj-poly-agent

# 2. Install dependencies
pip install -r requirements.txt --break-system-packages

# 3. Configure
cp .env.template .env
# Edit .env: set POLY_PRIVATE_KEY, API creds, DRY_RUN=True initially

# 4. Run (dry-run mode — no real orders)
python run_agent.py

# 5. Watch dashboard
open dashboard/live.html

# 6. When confident → set DRY_RUN=False in .env
```

---

## Risk Management

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `MAX_EXPOSURE` | 25% | Max bankroll deployed simultaneously |
| `MAX_SINGLE_BET` | 10% | Hard cap per position |
| `MAX_DAILY_LOSS` | $20 | Circuit-breaker — pauses agent |
| `MAX_POSITIONS` | 5 | Prevents over-diversification |
| `MIN_HURST` | 0.55 | Only trade exploitable regimes |
| `DRY_RUN` | True | Safe default — logs signals, no orders |

---

## Signal Pipeline

Every `SCAN_INTERVAL` (default 15 min):

1. Fetch top active markets (`volume > $5k`)
2. Pull CLOB price history per market (1-day fidelity)
3. Compute log-odds series → Hurst R/S
4. Compute EMA(12h)/EMA(48h) momentum
5. Fractal-adjust raw probability
6. Compute corrected half-Kelly for YES and NO sides
7. Filter: H > 0.55 AND Kelly > 0.5%
8. Pass through risk gates
9. Place limit order via py-clob-client
10. Write state → dashboard/live.json

---

## Case Study Results (simulation, 45 markets)

| Metric | Value |
|--------|-------|
| Markets with H > 0.55 | 31% |
| Avg Kelly (exploitable markets) | 4.2% |
| Expected EV per bet | +3.8% |
| Max observed Kelly | 18.7% |
| Bankroll: $100 | Max position: $10 |

*Live P&L updates in `dashboard/live.html` once agent is running.*

---

## Part of swaraj-engine

This agent is a demonstration application of the
[swaraj-engine](https://github.com/spalsh-spec/swaraj-engine) fractal analysis framework.

The same MFDFA / Hurst methodology applies to:
- Prediction markets (this repo)
- Electricity spot price mining optimization
- Crypto arbitrage (coming)
- Any time series with measurable autocorrelation

---

*Built by [@spalsh-spec](https://github.com/spalsh-spec) | fractal intelligence, asymmetric sizing*
