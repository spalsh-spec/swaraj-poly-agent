"""risk.py — position limits, exposure checks, daily loss circuit-breaker."""
from . import config


class RiskManager:
    def __init__(self):
        self.positions: dict[str, dict] = {}   # token_id → {side, size_usdc, entry_price}
        self.daily_pnl: float = 0.0
        self.paused: bool = False

    # ── Checks ───────────────────────────────────────────────────────────────
    def can_bet(self, bankroll: float) -> tuple[bool, str]:
        if self.paused:
            return False, "agent paused (daily loss limit hit)"
        if self.daily_pnl <= -config.MAX_DAILY_LOSS:
            self.paused = True
            return False, f"daily loss cap: PnL={self.daily_pnl:.2f}"
        if len(self.positions) >= config.MAX_POSITIONS:
            return False, f"max positions ({config.MAX_POSITIONS}) open"
        deployed = sum(p["size_usdc"] for p in self.positions.values())
        if deployed / bankroll >= config.MAX_EXPOSURE:
            return False, f"max exposure {config.MAX_EXPOSURE*100:.0f}% reached"
        return True, "ok"

    def size_bet(self, kelly_frac: float, bankroll: float) -> float:
        """Return dollar bet size respecting MAX_SINGLE_BET cap."""
        raw = kelly_frac * bankroll
        cap = config.MAX_SINGLE_BET * bankroll
        return round(min(raw, cap), 2)

    # ── Position tracking ─────────────────────────────────────────────────────
    def open_position(self, token_id: str, side: str, size_usdc: float, entry_price: float):
        self.positions[token_id] = {
            "side": side,
            "size_usdc": size_usdc,
            "entry_price": entry_price,
        }

    def close_position(self, token_id: str, exit_price: float):
        if token_id not in self.positions:
            return
        pos = self.positions.pop(token_id)
        if pos["side"] == "YES":
            pnl = pos["size_usdc"] * (exit_price - pos["entry_price"]) / pos["entry_price"]
        else:  # NO — price should fall
            pnl = pos["size_usdc"] * (pos["entry_price"] - exit_price) / (1 - pos["entry_price"] + 1e-9)
        self.daily_pnl += pnl
        return round(pnl, 4)

    def status(self) -> dict:
        deployed = sum(p["size_usdc"] for p in self.positions.values())
        return {
            "open_positions": len(self.positions),
            "deployed_usdc": round(deployed, 2),
            "daily_pnl": round(self.daily_pnl, 4),
            "paused": self.paused,
        }
