# Swaraj Poly Agent — Architectural Decisions

## ADR-001: Hurst Exponent threshold H > 0.55

**Decision:** Only trade markets where the Hurst exponent on log-odds increments exceeds 0.55.

**Rationale:** H = 0.5 = Brownian motion (random). H > 0.5 = persistent autocorrelation — the process has memory. At H > 0.55 we have strong evidence of persistence beyond noise. R/S analysis on 60-period windows (fidelity=60 min candles) with 169 data points over 1 week gives statistically stable estimates.

**Alternative considered:** Kelly criterion alone (no Hurst filter). Rejected: Kelly is myopic to regime — optimises bet size given probability edge but can't detect if price series is trending vs. mean-reverting. Hurst filters to persistent trends only.

**Reference:** Mandelbrot & Wallis (1969), Peters (1994) — Fractal Market Hypothesis.

---

## ADR-002: Half-Kelly with payoff correction

**Decision:** kelly_frac = (p_true - p_market) / (1 - p_market), then best_kelly = kelly_frac / 2.

**Rationale:** Full Kelly is mathematically optimal under certainty. In practice, p_true is estimated — estimation error means full Kelly overbets. Half-Kelly reduces volatility by ~75% while keeping ~85% of expected log growth. Payoff correction / (1 - p_market) accounts for Polymarket's binary structure.

**Alternative:** Fixed fraction 0.25 Kelly. Rejected: too conservative for H > 0.65 markets.

---

## ADR-003: Gamma API clobTokenIds parsing

**Decision:** clobTokenIds from Gamma API is a JSON-encoded string, not a Python list. Parse via json.loads() with fallback.

**Rationale:** The Gamma REST API returns clobTokenIds: '["tok1","tok2"]'. Direct indexing returns "[" (first character). Fixed in scanner.py v1.2 with _parse_clob_ids() helper. Before fix: 0 signals. After: 8+ per scan.

---

## ADR-004: DRY_RUN credential gate

**Decision:** POLY_PRIVATE_KEY validation only runs when DRY_RUN=False.

**Rationale:** DRY_RUN must work without live credentials for signal-quality testing and development.

---

## ADR-005: Atomic state writes

**Decision:** All state writes go to .tmp then os.replace().

**Rationale:** os.replace() is atomic on POSIX. Crash never leaves a half-written state file.

---

## ADR-006: condition_id deduplication

**Decision:** Track condition_ids in state; refuse to open both YES and NO on same condition.

**Rationale:** Opening both sides on same condition is self-defeating (wastes capital on fees). List persisted in state for restart safety.

---

## ADR-007: MAX_HOLD_DAYS = 7

**Decision:** Auto-close positions older than 7 days.

**Rationale:** Capital recycling. Hurst exponent decays toward 0.5 over time — the original signal becomes stale. Forced exit after 7 days recycles capital to fresh signals.
