"""
agent.py — async main loop
  scan → signal → risk-gate → execute → track

Architecture mirrors Renaissance Medallion:
  detect persistent autocorrelation (H > 0.55)
  size asymmetrically (half-Kelly, Polymarket payoff-adjusted)
  execute on CLOB with limit orders
"""
import asyncio, logging, time, json, os
from datetime import datetime

from . import config
from .scanner  import scan_markets
from .risk     import RiskManager
from .executor import Executor
from .tracker  import load_state, save_state, record_trade, print_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agent")

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "dashboard", "live.json")


class SwarajPolyAgent:
    def __init__(self):
        self.risk     = RiskManager()
        self.executor = Executor()
        self.state    = load_state()
        self.bankroll = config.BANKROLL_USDC
        self.cycle    = 0

    # ── Core cycle ────────────────────────────────────────────────────────────
    async def run_cycle(self):
        self.cycle += 1
        log.info(f"══ Cycle {self.cycle} | {datetime.utcnow().isoformat()}Z ══")
        log.info(f"   DRY_RUN={config.DRY_RUN} | Bankroll=${self.bankroll:.2f}")

        # 1. Scan for signals
        try:
            signals = await scan_markets()
        except Exception as e:
            log.error(f"scan_markets failed: {e}")
            return

        log.info(f"   Signals found: {len(signals)}")
        self._update_dashboard(signals)

        # 2. Process each signal through risk gate
        for sig in signals:
            ok, reason = self.risk.can_bet(self.bankroll)
            if not ok:
                log.warning(f"   Risk gate blocked: {reason}")
                break

            # Skip already-open positions
            if sig["token_id"] in self.risk.positions:
                continue

            bet_size = self.risk.size_bet(sig["best_kelly"], self.bankroll)
            if bet_size < 0.50:   # min $0.50 bet
                continue

            log.info(
                f"   SIGNAL  {sig['side']} | Q: {sig['question'][:60]}…\n"
                f"           H={sig['H']} {sig['regime']} | p_mkt={sig['p_market']} "
                f"p_true={sig['p_true']} | kelly={sig['best_kelly']:.3f} → ${bet_size:.2f}"
            )

            # 3. Execute
            resp = self.executor.place_limit(
                token_id=sig["token_id"],
                side=sig["side"],
                price=sig["p_market"],
                size_usdc=bet_size,
            )

            if resp.get("error"):
                log.error(f"   Order error: {resp['error']}")
                continue

            # 4. Track position
            self.risk.open_position(
                sig["token_id"], sig["side"], bet_size, sig["p_market"]
            )
            self.state["positions"][sig["token_id"]] = {
                "question": sig["question"],
                "side": sig["side"],
                "size_usdc": bet_size,
                "entry_price": sig["p_market"],
                "H": sig["H"],
                "regime": sig["regime"],
                "order": resp,
                "ts": int(time.time()),
            }
            save_state(self.state)

        print_summary(self.state)

    # ── Dashboard state dump ──────────────────────────────────────────────────
    def _update_dashboard(self, signals: list[dict]):
        payload = {
            "updated": datetime.utcnow().isoformat() + "Z",
            "dry_run": config.DRY_RUN,
            "bankroll": self.bankroll,
            "risk": self.risk.status(),
            "signals": signals[:20],
            "positions": list(self.state.get("positions", {}).values()),
            "daily_pnl": self.state.get("daily_pnl", 0),
            "total_pnl": self.state.get("total_pnl", 0),
        }
        try:
            os.makedirs(os.path.dirname(DASHBOARD_PATH), exist_ok=True)
            with open(DASHBOARD_PATH, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            log.warning(f"dashboard write failed: {e}")

    # ── Main event loop ───────────────────────────────────────────────────────
    async def run(self):
        log.info("🚀 swaraj-poly-agent starting")
        log.info(f"   DRY_RUN  = {config.DRY_RUN}")
        log.info(f"   BANKROLL = ${config.BANKROLL_USDC:.2f}")
        log.info(f"   MIN_HURST= {config.MIN_HURST}  MIN_KELLY={config.MIN_KELLY}")
        if config.DRY_RUN:
            log.warning("   ⚠️  DRY_RUN=True — no real orders will be placed")
            log.warning("   Set DRY_RUN=False in .env only after manual verification")

        last_scan = 0
        while True:
            now = time.time()
            if now - last_scan >= config.SCAN_INTERVAL:
                await self.run_cycle()
                last_scan = time.time()
            await asyncio.sleep(config.POLL_INTERVAL)
