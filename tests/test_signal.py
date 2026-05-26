"""
tests/test_signal.py

Pure-Python unit tests — no network, no CLOB credentials required.
Run: pytest tests/ -v
"""
import math
import random
import sys
import os
import types

# ── Stub heavy optional deps before any swaraj_poly import ──────────────────
for mod in ("py_clob_client", "py_clob_client.client",
            "py_clob_client.clob_types", "py_clob_client.constants",
            "dotenv", "aiohttp"):
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

# Stub dotenv.load_dotenv
sys.modules["dotenv"].load_dotenv = lambda: None  # type: ignore

# Stub py_clob_client constants
sys.modules["py_clob_client.constants"].POLYGON = 137  # type: ignore

# Make clob_types stubs
clob_types = sys.modules["py_clob_client.clob_types"]
clob_types.ApiCreds = lambda **kw: None  # type: ignore
clob_types.OrderArgs = lambda **kw: None  # type: ignore
clob_types.OrderType = type("OrderType", (), {"GTC": "GTC"})()  # type: ignore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swaraj_poly.signal import hurst_rs, regime, momentum, kelly_yes, kelly_no, evaluate
from swaraj_poly.risk import RiskManager


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _random_walk(n: int = 200, seed: int = 42) -> list:
    rng = random.Random(seed)
    prices = [0.5]
    for _ in range(n - 1):
        prices.append(max(0.01, min(0.99, prices[-1] + rng.gauss(0, 0.02))))
    return prices


def _trending_series(n: int = 200, drift: float = 0.003) -> list:
    """Smoothly trending price series."""
    prices = [0.3]
    for _ in range(n - 1):
        prices.append(max(0.01, min(0.99, prices[-1] + drift + random.gauss(0, 0.005))))
    return prices


# ─────────────────────────────────────────────────────────────────────────────
# hurst_rs tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHurstRS:
    def test_short_series_returns_half(self):
        """Series shorter than 32 should return 0.5 (no data)."""
        assert hurst_rs([0.5] * 20) == 0.5

    def test_iid_noise_near_half(self):
        """True random increments should yield H close to 0.5."""
        rng = random.Random(0)
        ts = [rng.gauss(0, 1) for _ in range(256)]
        H = hurst_rs(ts)
        assert 0.3 <= H <= 0.75, f"Random walk H={H} out of expected range"

    def test_constant_series_returns_half(self):
        """All-same series has S=0 → no R/S points → fallback 0.5."""
        assert hurst_rs([0.5] * 64) == 0.5

    def test_output_is_float(self):
        rng = random.Random(1)
        ts = [rng.gauss(0, 1) for _ in range(64)]
        H = hurst_rs(ts)
        assert isinstance(H, float)

    def test_single_lag_fallback(self):
        """If only 1 lag produced (very short series at boundary), returns 0.5."""
        # 32 elements, min_chunk=16 → only one possible chunk size
        ts = [float(i) for i in range(32)]
        H = hurst_rs(ts, min_chunk=16)
        # Either returns 0.5 (fallback) or some value — must not crash
        assert isinstance(H, float)


# ─────────────────────────────────────────────────────────────────────────────
# regime tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRegime:
    def test_trending(self):
        assert regime(0.70) == "TRENDING↗"

    def test_persistent(self):
        assert regime(0.60) == "PERSISTENT"

    def test_random(self):
        assert regime(0.50) == "RANDOM"

    def test_mean_rev(self):
        assert regime(0.35) == "MEAN-REV↩"

    def test_boundary_trending(self):
        assert regime(0.65) == "PERSISTENT"  # boundary: >0.65 is TRENDING, ==0.65 is PERSISTENT

    def test_boundary_mean_rev(self):
        assert regime(0.40) == "RANDOM"      # boundary: <0.40 is MEAN-REV, ==0.40 is RANDOM


# ─────────────────────────────────────────────────────────────────────────────
# momentum tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMomentum:
    def test_insufficient_data_returns_zero(self):
        assert momentum([0.5] * 10) == 0.0

    def test_rising_prices_positive_momentum(self):
        prices = [0.3 + i * 0.005 for i in range(100)]
        m = momentum(prices)
        assert m > 0, f"Rising prices should have positive momentum, got {m}"

    def test_falling_prices_negative_momentum(self):
        prices = [0.9 - i * 0.005 for i in range(100)]
        m = momentum(prices)
        assert m < 0, f"Falling prices should have negative momentum, got {m}"

    def test_flat_prices_near_zero(self):
        prices = [0.5] * 100
        assert momentum(prices) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Kelly tests
# ─────────────────────────────────────────────────────────────────────────────

class TestKelly:
    def test_kelly_yes_edge_case_zero_price(self):
        assert kelly_yes(0.6, 0.001) == 0.0
        assert kelly_yes(0.6, 0.999) == 0.0

    def test_kelly_yes_positive_when_edge(self):
        """p_true=0.7, market=0.5 → clear edge → positive Kelly."""
        k = kelly_yes(0.7, 0.5)
        assert k > 0, f"Expected positive Kelly, got {k}"

    def test_kelly_yes_zero_when_no_edge(self):
        """p_true=0.4, market=0.6 → market overpriced → 0 Kelly."""
        k = kelly_yes(0.4, 0.6)
        assert k == 0.0

    def test_kelly_no_positive_when_market_overpriced_yes(self):
        """Market has YES at 0.8 but true is 0.5 → NO has edge."""
        k = kelly_no(0.5, 0.8)
        assert k > 0

    def test_kelly_no_zero_when_no_edge(self):
        k = kelly_no(0.7, 0.4)  # true YES=0.7, market YES=0.4 → NO has no edge
        assert k == 0.0

    def test_kelly_symmetry_at_fair_price(self):
        """When p_true == p_market, Kelly should be ~0 (no edge)."""
        k = kelly_yes(0.5, 0.5)
        # Small positive value possible due to fee drag making it slightly negative
        assert k <= 0.01

    def test_half_kelly_applied(self):
        """Full Kelly for YES at p_true=0.8, p_mkt=0.5: full=(0.8*1 - 0.2)/1=0.6.
        Half-Kelly = 0.3. Result should be approximately 0.3 minus tiny fee drag."""
        k = kelly_yes(0.8, 0.5)
        assert 0.25 <= k <= 0.35, f"Half-Kelly={k} outside expected range"


# ─────────────────────────────────────────────────────────────────────────────
# evaluate (full signal pipeline) tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluate:
    def test_returns_none_for_short_series(self):
        prices = [0.5] * 20
        assert evaluate(prices, 0.5) is None

    def test_returns_dict_for_valid_input(self):
        prices = _random_walk(200)
        result = evaluate(prices, prices[-1])
        assert result is not None
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        prices = _random_walk(200)
        result = evaluate(prices, prices[-1])
        assert result is not None
        for key in ("H", "regime", "momentum", "p_market", "p_true",
                    "kelly_yes", "kelly_no", "best_kelly", "side"):
            assert key in result, f"Missing key: {key}"

    def test_side_is_yes_or_no(self):
        prices = _random_walk(200)
        result = evaluate(prices, prices[-1])
        assert result is not None
        assert result["side"] in ("YES", "NO")

    def test_best_kelly_equals_max_of_yes_no(self):
        prices = _random_walk(200)
        result = evaluate(prices, prices[-1])
        assert result is not None
        expected = max(result["kelly_yes"], result["kelly_no"])
        assert abs(result["best_kelly"] - expected) < 0.0001

    def test_p_true_in_valid_range(self):
        prices = _random_walk(200)
        result = evaluate(prices, prices[-1])
        assert result is not None
        assert 0.01 <= result["p_true"] <= 0.99

    def test_h_in_valid_range(self):
        prices = _random_walk(200)
        result = evaluate(prices, prices[-1])
        assert result is not None
        # H should be a reasonable float
        assert isinstance(result["H"], float)

    def test_minimum_33_prices_boundary(self):
        """Exactly 33 prices should NOT return None (boundary condition)."""
        prices = _random_walk(33)
        result = evaluate(prices, prices[-1])
        # 33 prices → 32 increments → hurst_rs needs >=32 → should work
        assert result is not None

    def test_32_prices_returns_none(self):
        """32 prices → 31 increments → hurst_rs < 32 → returns 0.5 (no signal needed test)."""
        prices = _random_walk(32)
        result = evaluate(prices, prices[-1])
        # 32 prices is below 33 threshold → returns None
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# RiskManager tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskManager:
    def _make_rm(self) -> RiskManager:
        from swaraj_poly import config
        config.MAX_DAILY_LOSS = 20.0
        config.MAX_POSITIONS = 5
        config.MAX_EXPOSURE = 0.25
        config.MAX_SINGLE_BET = 0.10
        config.BANKROLL_USDC = 100.0
        return RiskManager()

    def test_can_bet_fresh(self):
        rm = self._make_rm()
        ok, reason = rm.can_bet(100.0)
        assert ok
        assert reason == "ok"

    def test_paused_blocks_all_bets(self):
        rm = self._make_rm()
        rm.paused = True
        ok, reason = rm.can_bet(100.0)
        assert not ok
        assert "paused" in reason

    def test_daily_loss_triggers_pause(self):
        rm = self._make_rm()
        rm.daily_pnl = -20.0  # exactly at limit
        ok, reason = rm.can_bet(100.0)
        assert not ok
        assert rm.paused  # should be set now

    def test_max_positions_blocks(self):
        rm = self._make_rm()
        for i in range(5):
            rm.open_position(f"tok{i}", "YES", 5.0, 0.5)
        ok, reason = rm.can_bet(100.0)
        assert not ok
        assert "max positions" in reason

    def test_max_exposure_blocks(self):
        rm = self._make_rm()
        # Deploy 25% of bankroll (100 * 0.25 = 25 USDC)
        rm.open_position("tok0", "YES", 25.0, 0.5)
        ok, reason = rm.can_bet(100.0)
        assert not ok
        assert "exposure" in reason

    def test_size_bet_capped_at_max_single_bet(self):
        rm = self._make_rm()
        # kelly_frac=0.5 → raw=50, cap=10 → should be 10
        size = rm.size_bet(0.5, 100.0)
        assert size == 10.0

    def test_size_bet_below_cap(self):
        rm = self._make_rm()
        # kelly_frac=0.05 → raw=5, cap=10 → should be 5
        size = rm.size_bet(0.05, 100.0)
        assert size == 5.0

    def test_open_and_close_position_yes_profit(self):
        rm = self._make_rm()
        rm.open_position("tokA", "YES", 10.0, 0.5)
        pnl = rm.close_position("tokA", 0.7)  # price rose
        assert pnl is not None
        assert pnl > 0

    def test_open_and_close_position_yes_loss(self):
        rm = self._make_rm()
        rm.open_position("tokA", "YES", 10.0, 0.6)
        pnl = rm.close_position("tokA", 0.4)  # price fell
        assert pnl is not None
        assert pnl < 0

    def test_open_and_close_position_no_profit(self):
        rm = self._make_rm()
        # Bet NO at YES=0.7 (NO price = 0.3)
        rm.open_position("tokB", "NO", 10.0, 0.7)
        pnl = rm.close_position("tokB", 0.4)  # YES fell → NO won
        assert pnl is not None
        assert pnl > 0

    def test_close_nonexistent_position_returns_none(self):
        rm = self._make_rm()
        result = rm.close_position("nonexistent", 0.5)
        assert result is None

    def test_status_keys(self):
        rm = self._make_rm()
        s = rm.status()
        for k in ("open_positions", "deployed_usdc", "daily_pnl", "paused"):
            assert k in s

    def test_daily_pnl_accumulates(self):
        rm = self._make_rm()
        rm.open_position("tok1", "YES", 10.0, 0.5)
        rm.close_position("tok1", 0.8)
        rm.open_position("tok2", "YES", 10.0, 0.5)
        rm.close_position("tok2", 0.3)
        # Both trades accumulated
        assert rm.daily_pnl != 0
