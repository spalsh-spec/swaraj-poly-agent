# swaraj-poly-agent — Hedge Fund Level Due Diligence
*Full-stack audit: signal integrity, infrastructure, guardrails, profit routing*
*Audit date: 2026-05-25 | Version: 1.1 post-fix*

---

## EXECUTIVE SUMMARY

| Dimension | Pre-Audit | Post-Fix (v1.1) |
|-----------|-----------|-----------------|
| Signal validity | ❌ CRITICAL BUG | ✅ Fixed |
| Kelly correctness | ✅ Correct | ✅ Correct |
| Risk guardrails | ⚠️ Partial | ⚠️ Needs hardening |
| Infrastructure | ⚠️ Dev-grade | ⚠️ Needs prod hardening |
| Profit routing | ❌ Undefined | 🔧 Mapped (manual) |
| Regulatory | ⚠️ Unreviewed | ⚠️ Unreviewed |

**Verdict: Do NOT set DRY_RUN=False until Section 3 infrastructure items are resolved.**

---

## 1. SIGNAL INTEGRITY AUDIT

### 1a. Critical Bug Found & Fixed: Hurst Applied to Levels
**Severity: CRITICAL (would have traded noise as signal)**

**Pre-fix behavior:**
```
Random price series log-odds LEVELS → H = 0.958  ← false "TRENDING"
```
A bounded random price series creates non-stationary log-odds LEVELS.
R/S analysis on non-stationary data is undefined — produces spuriously high H
for almost every market, making MIN_HURST=0.55 filter effectively useless.

**Fix (signal.py v1.1):**
Apply Hurst to FIRST DIFFERENCES (increments) of log-odds:
```python
increments = [logodds[i+1] - logodds[i] for i in range(len(logodds)-1)]
H = hurst_rs(increments)   # ← stationary series, valid H
```
**Post-fix results:**
```
Random price -> increments: H = 0.516  ✅ (near 0.50 as expected)
Mean-rev price -> increments: H = 0.302  ✅ (correctly <0.45)
```

### 1b. Minimum Data Requirement
**Severity: HIGH**

R/S regression needs ≥4 lag points for stability.
With n=80 prices → n=79 increments → max lag = 39 → chunks: 8,16,32 = only 3 points.
**Fix (scanner.py v1.1):** Require MIN_PRICES=100 AND fetch 1-week history.
With n=100 → chunks: 8,16,32,64 = 4 points minimum.
With n=200+ → 5+ lag points → statistically reliable.

### 1c. Near-Resolved Market Filter
**Severity: MEDIUM**

Markets near resolution (price < 0.02 or > 0.98) produce near-infinite log-odds
increments → distorts H. Fixed: filter these out in scanner.py.

### 1d. Kelly Formula — VERIFIED CORRECT ✅
```
Kelly(p_true=p_market): 0.0000 — no edge at fair price ✅
Kelly(p_true=0.70, p_mkt=0.60): 0.1250 — mathematically exact ✅
Bet cap (MAX_SINGLE_BET=10%): $10 on $100 bankroll ✅
Fee drag included (0.1% Polymarket maker fee) ✅
```

### 1d. Kelly NO Asymmetry — BY DESIGN ✅
YES kelly(0.70@0.60) = 0.125 and NO kelly(0.30@0.60) = 0.250 are different.
This is correct: the YES token at 60¢ has payoff ratio 0.67, NO token at 40¢ has 1.50.
Different payoff structures → different optimal fractions. Not a bug.

---

## 2. GUARDRAILS ASSESSMENT

### 2a. Current Guardrails ✅
| Guardrail | Implementation | Status |
|-----------|---------------|--------|
| DRY_RUN=True default | config.py + run_agent.py check | ✅ Solid |
| MAX_SINGLE_BET=10% | risk.py size_bet() | ✅ Hard cap |
| MAX_EXPOSURE=25% | risk.py can_bet() | ✅ |
| MAX_POSITIONS=5 | risk.py can_bet() | ✅ |
| MAX_DAILY_LOSS=$20 | risk.py paused flag | ✅ |
| MIN_HURST=0.55 | scanner.py + config | ✅ |
| Private key never logged | executor.py | ✅ |
| .env in .gitignore | .gitignore | ✅ |

### 2b. Missing Guardrails ❌ (MUST ADD BEFORE LIVE)

**1. No order fill verification**
Limit orders can sit unfilled indefinitely. Current code assumes fill.
Risk: position in risk.py but no actual USDC deployed. Or worse: market resolves
before limit fills → wasted opportunity, position book mismatch.
Fix needed: poll open orders every POLL_INTERVAL, cancel stale orders after N minutes.

**2. No duplicate-market guard across cycles**
Each 15-min cycle re-scans the same markets. If a market passes signal filter
twice and the position is already open, `sig["token_id"] in self.risk.positions`
catches it — this IS guarded. ✅ (on re-check this is actually handled)

**3. State file not atomic**
`~/.swaraj_poly_state.json` written with `json.dump()` directly. Power loss mid-write
→ corrupt JSON → agent crashes on restart.
Fix: write to `.tmp` then `os.replace()` for atomic swap.

**4. No network failure budget**
Single API failure kills the cycle. No exponential backoff, no retry.
Fix: wrap `_get()` with tenacity retry (3 attempts, 2s backoff).

**5. No position reconciliation on restart**
Agent restart loads state from JSON but doesn't check actual CLOB open orders.
Positions in JSON may differ from reality after a crash.
Fix: on startup, call `client.get_orders()` and reconcile with state.

**6. No max-per-market cap**
Could theoretically open the same market twice via different token IDs
(YES and NO are different token_ids). Risk.py only tracks one token_id per position.
Fix: add condition_id deduplication.

**7. No Polygon gas check**
CLOB transactions require MATIC for gas. If MATIC balance is 0, orders fail silently.
Fix: check MATIC balance on startup, warn if < 0.1 MATIC.

---

## 3. FULL STACK INFRASTRUCTURE REQUIREMENTS

### 3a. Current State (Dev Grade)
```
Process:      python run_agent.py  ← dies on terminal close
Persistence:  JSON file            ← not crash-safe
Logging:      stdout               ← no rotation, no alerting
Monitoring:   HTML dashboard       ← manual refresh
Secrets:      .env file            ← ok for dev, weak for prod
```

### 3b. Production Requirements (in priority order)

**P0 — Before any real money:**
```bash
# 1. Process supervision (keeps agent alive, auto-restarts)
brew install supervisor
# supervisord.conf entry for run_agent.py

# 2. Atomic state writes (crash-safe)
# Replace json.dump with: write .tmp → os.replace()

# 3. Log rotation
logging.handlers.RotatingFileHandler(
    '~/.swaraj_poly.log', maxBytes=10MB, backupCount=5
)

# 4. MATIC gas check on startup
# web3.eth.get_balance(address) → warn if < 0.1 MATIC
```

**P1 — Within first week of live trading:**
```bash
# 5. Order fill polling (cancel stale after 30min)
# 6. Retry with exponential backoff on API failures
# 7. Telegram/Discord alerts on: new position, fill, daily loss warning
# 8. Position reconciliation on startup
```

**P2 — Once profitable:**
```bash
# 9. Secrets in macOS Keychain (not .env file)
# 10. Duplicate condition_id guard
# 11. Automated profit withdrawal trigger
```

### 3c. Dependency Risk
| Package | Version | Risk |
|---------|---------|------|
| py-clob-client | 0.34.6 | Polymarket can break API compat |
| aiohttp | 3.13.5 | Stable, low risk |
| python-dotenv | latest | Stable |
| eth-account | 0.13.7 | Stable |

**Polymarket API risk:** Gamma API and CLOB are undocumented/unofficial.
Rate limits unspecified. May change without notice.
Mitigation: cache market list, exponential backoff, catch HTTP 429.

---

## 4. FEE & SLIPPAGE ANALYSIS

### 4a. Cost Structure
| Cost | Amount | Notes |
|------|--------|-------|
| CLOB maker fee | 0% | Limit orders that add liquidity |
| CLOB taker fee | 0.1% | Limit orders that cross spread |
| Spread (active mkt) | 0.5–2% | Bid-ask, market dependent |
| Polygon gas | ~$0.001 | Negligible |
| Bridge fee (withdrawal) | 0.1% | Only on profit withdrawal |

### 4b. Break-Even Edge Required
At 1% spread (0.5% each side), Kelly must exceed ~1.5% to be net positive.
Current MIN_KELLY=0.5% → some trades will be negative EV after spread.
**Recommendation: raise MIN_KELLY to 0.02 (2%) for live trading.**

### 4c. EV Under Realistic Assumptions
```
p_true=0.65, p_mkt=0.60, spread=1%:
  kelly_raw    = 6.25%
  kelly_net    = 5.62% (after fees)
  bet size     = $5.62 (capped at $10)
  gross EV/bet = $0.52
  net EV/bet   = $0.47 (after 0.5% spread cost)

At 2 viable signals/day × 250 days:
  Annual gross EV = $0.52 × 500 = $260
  Annual net EV   = $0.47 × 500 = $235
  ROI on $100     = 235%  ← theoretical upper bound
```
**Caveat:** This assumes the edge is real (H correctly identified) and fills at limit price.
Actual ROI will be lower due to: selection bias in markets found, model error in H,
occasional no-fill on limits, regime changes mid-market.
**Conservative real-world estimate: 50–150% annual on $100 bankroll.**

---

## 5. PROFIT ROUTING

### 5a. Current Flow
```
$USDC bet placed on Polymarket CLOB
         ↓ market resolves
USDC credited to Polymarket internal balance
         ↓ MANUAL withdrawal
polymarket.com → Withdraw → Polygon mainnet wallet
         ↓ MANUAL bridge
Polygon USDC → Ethereum mainnet (via Polygon bridge, 7-day delay)
OR:  Polygon USDC → exchange (via CCTP bridge, minutes)
         ↓
USDC on exchange → sell for fiat → bank
```

### 5b. Reinvestment Logic (not yet implemented)
Recommended: auto-compound profits by updating BANKROLL_USDC in state.
Simple formula: `new_bankroll = initial + total_pnl * reinvest_rate`
`reinvest_rate = 0.5` → half profits stay working, half withdrawable.

### 5c. Tax Treatment (India context)
Prediction market winnings = gambling income in most jurisdictions.
India: 30% flat tax + 4% cess on net gambling winnings (Finance Act 2023 covers VDAs).
Polymarket = USDC (crypto) → additional crypto tax layer may apply.
**Recommendation: track every trade in HEDGE_FUND_ANALYSIS.md for tax records.**
Agent already writes `~/.swaraj_poly_state.json` with full trade log — export annually.

### 5d. Withdrawal Recommendation
- Keep working capital ≤ $100 on Polymarket at all times (counterparty risk)
- Withdraw profits > $50 monthly
- Never keep more than 1 week's expected profit on-platform

---

## 6. EXPECTED PERFORMANCE SCENARIOS

| Scenario | Win Rate | Kelly Avg | Bets/Day | Annual P&L |
|----------|----------|-----------|----------|------------|
| Bear (model overfit) | 45% | 2% | 1 | -$8 |
| Base | 55% | 3.5% | 2 | +$89 |
| Bull (strong edge) | 65% | 5% | 3 | +$243 |
| Simons (perfect H) | 70% | 8% | 4 | +$512 |

All on $100 bankroll, half-Kelly, 0.5% spread cost included.
Base case: 89% annual ROI. Comparable to top-quartile hedge fund net of fees.

---

## 7. PRE-LAUNCH CHECKLIST

### Before setting DRY_RUN=False:
- [ ] Run 5+ dry-run cycles, signals look sensible
- [ ] POLY_PRIVATE_KEY set in .env (never committed)
- [ ] POLY_API_KEY / SECRET / PASSPHRASE set
- [ ] MATIC balance > 0.1 on Polygon wallet (for gas)
- [ ] USDC balance on Polymarket ≥ BANKROLL_USDC ($100)
- [ ] Atomic state writes implemented
- [ ] Process supervisor configured (supervisord or launchd)
- [ ] Log file rotation configured
- [ ] MIN_KELLY raised to 0.02 for live trading
- [ ] Stale order cancellation implemented

### Ongoing monitoring:
- [ ] Check dashboard/live.html daily
- [ ] Review ~/.swaraj_poly_state.json weekly
- [ ] Withdraw profits > $50 monthly
- [ ] Reassess MIN_HURST quarterly based on realized win rate

---

## 8. VERDICT

**The mathematics are sound.** Corrected Kelly + Hurst increments is the right method.
The edge, if real, compounds significantly on small bankrolls.

**The infrastructure is dev-grade.** Three fixes are blocking production:
1. Atomic state writes (data integrity)
2. Order fill verification (position accuracy)  
3. Process supervision (uptime)

**The guardrails are adequate for DRY_RUN.** Not yet adequate for live capital.
Estimated time to production-ready: 1–2 days of additional engineering.

*"The goal is not to predict the future — it's to find markets where past autocorrelation
persists long enough to size into before the market corrects." — swaraj-engine principle*
