"""
agent.py — async main loop: scan → signal → risk-gate → execute → track

Architecture mirrors Renaissance Medallion:
  detect persistent autocorrelation (H > 0.55 on increments of log-odds)
  size asymmetrically (half-Kelly, Polymarket payoff-adjusted)
  execute on CLOB with GTC limit orders + fill verification

Guardrails implemented here:
  P0:  atomic state via tracker.save_state()
  P0:  fill verify + stale-order cancel via executor.verify_fill()
  P1:  condition_id deduplication (no YES+NO on same market)
  P1:  MATIC gas balance check on startup
  P1:  exponential backoff already in executor._with_backoff()
"""
from __future__ import annotations
import asyncio, logging, time, json, os
from datetime import datetime

from . import config
from .scanner    import scan_markets
from .risk       import RiskManager
from .executor   import Executor
from .tracker    import load_state, save_state, record_trade, print_summary
from .signal_log import log_signals, signal_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agent")

DASHBOARD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "dashboard", "live.json"
)
MIN_MATIC_GAS = float(getattr(config, "MIN_MATIC_GAS", 0.05))


def _check_matic_balance() -> bool:
    """P1: Verify Polygon wallet has enough MATIC for gas before live trading."""
    if config.DRY_RUN:
        log.info("[MATIC CHECK] DRY_RUN — skipping gas balance check")
        return True
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        addr = w3.eth.account.from_key(config.POLY_PRIVATE_KEY).address
        bal  = w3.from_wei(w3.eth.get_balance(addr), "ether")
        log.info(f"[MATIC CHECK] wallet={addr[:10]}… balance={bal:.4f} MATIC")
        if float(bal) < MIN_MATIC_GAS:
            log.error(
                f"[MATIC CHECK] INSUFFICIENT GAS: {bal:.4f} < {MIN_MATIC_GAS} MATIC"
                " — top up wallet before live trading"
            )
            return False
        return True
    except ImportError:
        log.warning("[MATIC CHECK] web3 not installed — skipping (pip install web3)")
        return True
    except Exception as e:
        log.warning(f"[MATIC CHECK] failed ({e}) — proceeding cautiously")
        return True   # don't block on RPC flakiness


class SwarajPolyAgent:
    def __init__(self):
        self.risk     = RiskManager()
        self.executor = Executor()
        self.state    = load_state()
        self.bankroll = config.BANKROLL_USDC
        self.cycle    = 0

    # ── P1: condition_id dedup helper ─────────────────────────────────────────
    def _condition_open(self, condition_id: str) -> bool:
        """True if we already have a bet on this condition_id."""
        return condition_id in self.state.get("condition_ids", [])

    def _register_condition(self, condition_id: str):
        ids = self.state.setdefault("condition_ids", [])
        if condition_id not in ids:
            ids.append(condition_id)

    def _deregister_condition(self, condition_id: str):
        ids = self.state.get("condition_ids", [])
        if condition_id in ids:
            ids.remove(condition_id)

    # ── Position close cycle ──────────────────────────────────────────────────
    async def close_positions_cycle(self):
        """Check open positions; close any that have resolved or are > MAX_HOLD_DAYS old.

        Fetches current mid-price from CLOB for each open token and calls
        risk.close_position() to realise P&L.

        MAX_HOLD_DAYS defaults to 7 — configurable via config.MAX_HOLD_DAYS env var.
        """
        MAX_HOLD_DAYS = int(getattr(config, "MAX_HOLD_DAYS", 7))
        cutoff_ts     = int(time.time()) - MAX_HOLD_DAYS * 86400
        positions     = dict(self.state.get("positions", {}))

        if not positions:
            return

        for token_id, pos in positions.items():
            age_days = (time.time() - pos.get("ts", 0)) / 86400

            # ── Try to fetch current CLOB mid-price ───────────────────────
            exit_price = None
            if not config.DRY_RUN:
                try:
                    book = await asyncio.get_running_loop().run_in_executor(
                        None, self.executor._c().get_order_book, token_id
                    )
                    bids = book.get("bids") or []
                    asks = book.get("asks") or []
                    best_bid = float(bids[0]["price"]) if bids else None
                    best_ask = float(asks[0]["price"]) if asks else None
                    if best_bid and best_ask:
                        exit_price = round((best_bid + best_ask) / 2, 4)
                except Exception as e:
                    log.warning(f"[CLOSE] price fetch failed for {token_id[:16]}: {e}")

            # ── In dry_run use entry_price as exit (zero P&L, records close) ─
            if config.DRY_RUN:
                exit_price = pos.get("entry_price", 0.5)

            if exit_price is None:
                continue   # can't close without price

            # ── Close if: > MAX_HOLD_DAYS old, or market price hit 0.02/0.98 ─
            resolved = exit_price <= 0.02 or exit_price >= 0.98
            stale    = pos.get("ts", 0) < cutoff_ts

            if not (resolved or stale):
                continue

            reason = "resolved" if resolved else f"stale>{MAX_HOLD_DAYS}d"
            pnl = self.risk.close_position(token_id, exit_price) or 0.0

            from .tracker import record_trade
            record_trade(self.state, {
                "token_id":    token_id,
                "question":    pos.get("question", ""),
                "side":        pos.get("side", ""),
                "size_usdc":   pos.get("size_usdc", 0),
                "entry_price": pos.get("entry_price", 0),
                "exit_price":  exit_price,
                "pnl":         pnl,
                "reason":      reason,
                "age_days":    round(age_days, 2),
            })

            # Remove from state
            self.state["positions"].pop(token_id, None)
            cid = pos.get("condition_id", "")
            if cid:
                self._deregister_condition(cid)

            log.info(
                f"[CLOSE] {pos.get('side')} {pos.get('question','')[:50]}… "
                f"exit={exit_price:.3f} pnl={pnl:+.4f} reason={reason}"
            )

        self.state["daily_pnl"]  = round(self.risk.daily_pnl, 4)
        from .tracker import save_state
        save_state(self.state)

    # ── Core cycle ────────────────────────────────────────────────────────────
    async def run_cycle(self):
        self.cycle += 1
        log.info(f"══ Cycle {self.cycle} | {datetime.utcnow().isoformat()}Z ══")
        log.info(f"   DRY_RUN={config.DRY_RUN} | Bankroll=${self.bankroll:.2f}")

        # 0. Close resolved / stale positions first
        await self.close_positions_cycle()

        # 1. Scan
        try:
            signals = await scan_markets()
        except Exception as e:
            log.error(f"scan_markets failed: {e}")
            return

        log.info(f"   Signals found: {len(signals)}")
        log_signals(signals)   # persist to dashboard/signals_log.csv
        self._update_dashboard(signals)

        # 2. Process signals through risk gate
        for sig in signals:
            ok, reason = self.risk.can_bet(self.bankroll)
            if not ok:
                log.warning(f"   Risk gate blocked: {reason}")
                break

            # Skip already-open token_id
            if sig["token_id"] in self.risk.positions:
                continue

            # P1: Skip if another bet already open on same condition_id
            cid = sig.get("condition_id", "")
            if cid and self._condition_open(cid):
                log.info(
                    f"   [DEDUP] Skipping {sig['side']} — already betting on "
                    f"condition {cid[:16]}"
                )
                continue

            bet_size = self.risk.size_bet(sig["best_kelly"], self.bankroll)
            if bet_size < 0.50:
                continue

            log.info(
                f"   SIGNAL  {sig['side']} | {sig['question'][:60]}…\n"
                f"           H={sig['H']} {sig['regime']} "
                f"p_mkt={sig['p_market']} p_true={sig['p_true']} "
                f"kelly={sig['best_kelly']:.3f} → ${bet_size:.2f}"
            )

            # 3. Execute
            placed_at = int(time.time())
            resp = self.executor.place_limit(
                token_id=sig["token_id"],
                side=sig["side"],
                price=sig["p_market"],
                size_usdc=bet_size,
            )

            if resp.get("error"):
                log.error(f"   Order error: {resp['error']}")
                continue

            order_id = resp.get("orderID", "")

            # P0: verify fill (async — run in thread so loop stays non-blocking)
            # FIX: use asyncio.get_running_loop() — get_event_loop() is deprecated in 3.10+
            fill_result = await asyncio.get_running_loop().run_in_executor(
                None, self.executor.verify_fill, order_id, placed_at
            )
            log.info(f"   Fill result: {fill_result}")

            if fill_result in ("timeout", "cancelled", "expired"):
                log.warning(f"   Order {order_id[:16]} not filled — skipping position record")
                # Remove stale order if tracked
                self.state.get("open_orders", {}).pop(order_id, None)
                save_state(self.state)
                continue

            # 4. Track position (only after confirmed fill or dry_run)
            if cid:
                self._register_condition(cid)

            self.risk.open_position(
                sig["token_id"], sig["side"], bet_size, sig["p_market"]
            )
            self.state["positions"][sig["token_id"]] = {
                "question":    sig["question"],
                "condition_id": cid,
                "side":        sig["side"],
                "size_usdc":   bet_size,
                "entry_price": sig["p_market"],
                "H":           sig["H"],
                "regime":      sig["regime"],
                "order_id":    order_id,
                "fill":        fill_result,
                "ts":          placed_at,
            }
            # Track in open_orders for reconciliation
            self.state.setdefault("open_orders", {})[order_id] = {
                "token_id":  sig["token_id"],
                "side":      sig["side"],
                "size_usdc": bet_size,
                "ts":        placed_at,
            }
            save_state(self.state)   # atomic write via tracker

        print_summary(self.state)

    # ── Dashboard state dump ──────────────────────────────────────────────────
    def _update_dashboard(self, signals: list):
        payload = {
            "updated":       datetime.utcnow().isoformat() + "Z",
            "dry_run":       config.DRY_RUN,
            "bankroll":      self.bankroll,
            "risk":          self.risk.status(),
            "signals":       signals[:20],
            "positions":     list(self.state.get("positions", {}).values()),
            "daily_pnl":     self.state.get("daily_pnl", 0),
            "total_pnl":     self.state.get("total_pnl", 0),
            "signal_stats":  signal_stats(),
        }
        try:
            os.makedirs(os.path.dirname(DASHBOARD_PATH), exist_ok=True)
            tmp = DASHBOARD_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, DASHBOARD_PATH)   # atomic dashboard write too
        except Exception as e:
            log.warning(f"dashboard write failed: {e}")

    # ── Main event loop ───────────────────────────────────────────────────────
    async def run(self):
        log.info("swaraj-poly-agent starting")
        log.info(f"   DRY_RUN  = {config.DRY_RUN}")
        log.info(f"   BANKROLL = ${config.BANKROLL_USDC:.2f}")
        log.info(f"   MIN_HURST= {config.MIN_HURST}  MIN_KELLY={config.MIN_KELLY}")

        if config.DRY_RUN:
            log.warning("   DRY_RUN=True — no real orders will be placed")

        # P1: MATIC gas check
        if not _check_matic_balance():
            log.error("   ABORT — insufficient MATIC gas. Top up then restart.")
            return

        # P1: Reconcile open orders vs CLOB on startup
        self.state["open_orders"] = self.executor.reconcile_open_orders(self.state)
        save_state(self.state)

        last_scan = 0
        while True:
            now = time.time()
            if now - last_scan >= config.SCAN_INTERVAL:
                await self.run_cycle()
                last_scan = time.time()
            await asyncio.sleep(config.POLL_INTERVAL)
