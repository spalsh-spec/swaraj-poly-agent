"""signal.py — Hurst R/S + corrected Kelly criterion (Simons methodology).

CRITICAL FIX (v1.1): Apply Hurst to INCREMENTS of log-odds, not levels.
Log-odds of bounded price series creates spurious persistence in levels.
First-differencing yields stationary series → correct H ≈ 0.5 for random,
H > 0.6 for genuinely trending, H < 0.4 for mean-reverting.
"""
from __future__ import annotations
import math
from typing import Optional, List


# ── Hurst exponent via R/S analysis ─────────────────────────────────────────
def hurst_rs(ts: List[float], min_chunk: int = 8) -> float:
    """Return Hurst exponent H for time series ts (must be stationary).
    H > 0.55 → persistent/trending (exploitable autocorrelation)
    H < 0.45 → mean-reverting
    H ≈ 0.50 → random walk (no edge)
    """
    n = len(ts)
    if n < 32:
        return 0.5
    lags, rs_vals = [], []
    chunk = min_chunk
    while chunk <= n // 2:
        rs_list = []
        for start in range(0, n - chunk + 1, chunk):
            sub = ts[start : start + chunk]
            m = sum(sub) / len(sub)
            dev = [x - m for x in sub]
            cum = [sum(dev[:i+1]) for i in range(len(dev))]
            R = max(cum) - min(cum)
            S = (sum((x - m) ** 2 for x in sub) / len(sub)) ** 0.5
            if S > 0:
                rs_list.append(R / S)
        if rs_list:
            lags.append(math.log(chunk))
            rs_vals.append(math.log(sum(rs_list) / len(rs_list)))
        chunk *= 2
    n2 = len(lags)
    if n2 < 2:
        return 0.5
    mx = sum(lags) / n2
    my = sum(rs_vals) / n2
    num = sum((lags[i] - mx) * (rs_vals[i] - my) for i in range(n2))
    den = sum((lags[i] - mx) ** 2 for i in range(n2))
    return num / den if den > 0 else 0.5


def regime(H: float) -> str:
    if H > 0.65:   return "TRENDING↗"
    if H > 0.55:   return "PERSISTENT"
    if H < 0.40:   return "MEAN-REV↩"
    return "RANDOM"


# ── EMA momentum ─────────────────────────────────────────────────────────────
def _ema(series: List[float], span: int) -> List[float]:
    k = 2 / (span + 1)
    out = [series[0]]
    for v in series[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def momentum(prices: List[float], short: int = 12, long: int = 48) -> float:
    """EMA crossover momentum: positive → drifting up, negative → drifting down."""
    if len(prices) < long + 1:
        return 0.0
    return _ema(prices, short)[-1] - _ema(prices, long)[-1]


# ── Fractal-adjusted probability ──────────────────────────────────────────────
def adjust_prob(p_raw: float, H: float, mom: float) -> float:
    """Shift raw market probability using fractal regime + momentum."""
    r = regime(H)
    if r in ("TRENDING↗", "PERSISTENT"):
        weight = min(0.12, abs(mom) * 2)
        delta = weight if mom > 0 else -weight
        return max(0.01, min(0.99, p_raw + delta))
    if r == "MEAN-REV↩":
        return p_raw * 0.85 + 0.5 * 0.15
    return p_raw


# ── Corrected Kelly for asymmetric Polymarket payoffs ─────────────────────────
def kelly_yes(p_true: float, p_market: float, fee: float = 0.001) -> float:
    """Half-Kelly fraction for a YES bet at price p_market (0–1).
    fee: Polymarket taker fee (0.1% on CLOB limit orders that cross spread).
    Limit orders as maker = 0 fee; using 0.001 as conservative estimate.
    """
    if p_market >= 0.999 or p_market <= 0.001:
        return 0.0
    b = (1 - p_market) / p_market
    k = (p_true * b - (1 - p_true)) / b
    k_net = k - fee / b          # fee drag
    return max(0.0, k_net / 2)   # half-Kelly


def kelly_no(p_true_yes: float, p_market_yes: float, fee: float = 0.001) -> float:
    """Half-Kelly fraction for a NO bet.
    p_true_yes: our estimate of YES probability
    p_market_yes: current YES token mid-price
    """
    p_no_true   = 1 - p_true_yes
    p_market_no = 1 - p_market_yes
    if p_market_no >= 0.999 or p_market_no <= 0.001:
        return 0.0
    b = (1 - p_market_no) / p_market_no
    k = (p_no_true * b - (1 - p_no_true)) / b
    k_net = k - fee / b
    return max(0.0, k_net / 2)


# ── Full signal evaluation ────────────────────────────────────────────────────
def evaluate(prices: List[float], market_price: float) -> Optional[dict]:
    """
    Given a token price history and current market price, return a signal dict.

    FIX v1.1: Apply Hurst to INCREMENTS of log-odds (first differences),
    not levels. Bounded series log-odds levels are non-stationary and produce
    spuriously high H even for random markets (H≈0.95 on noise → false signals).
    Increments are stationary: H≈0.50 random, H>0.6 trending, H<0.4 mean-rev.
    """
    if len(prices) < 33:   # need n+1 for increments
        return None

    def safe_logodds(p: float) -> float:
        p = max(0.001, min(0.999, p))
        return math.log(p / (1 - p))

    logodds = [safe_logodds(p) for p in prices]
    # FIXED: use increments (first differences) for stationarity
    increments = [logodds[i+1] - logodds[i] for i in range(len(logodds)-1)]

    H = hurst_rs(increments)
    mom = momentum(prices)
    p_true = adjust_prob(market_price, H, mom)
    k_yes = kelly_yes(p_true, market_price)
    k_no  = kelly_no(p_true, market_price)
    best_k = k_yes if k_yes >= k_no else k_no
    side = "YES" if k_yes >= k_no else "NO"

    return {
        "H": round(H, 4),
        "regime": regime(H),
        "momentum": round(mom, 5),
        "p_market": round(market_price, 4),
        "p_true": round(p_true, 4),
        "kelly_yes": round(k_yes, 4),
        "kelly_no": round(k_no, 4),
        "best_kelly": round(best_k, 4),
        "side": side,
    }
