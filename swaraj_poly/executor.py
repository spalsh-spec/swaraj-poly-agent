"""executor.py — place/cancel orders via py-clob-client (CLOB API).

Guardrails implemented:
  P0-a: verify_fill() — poll order status after placement
  P0-b: cancel_stale() — cancel GTC orders older than ORDER_FILL_TIMEOUT
  P1:   exponential backoff on transient API errors (3 retries, 2^n×2s)
"""
from __future__ import annotations
import asyncio, logging, time
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.constants import POLYGON

from . import config

log = logging.getLogger("executor")

ORDER_FILL_TIMEOUT = int(getattr(config, "ORDER_FILL_TIMEOUT", 300))  # 5 min
RETRY_MAX          = int(getattr(config, "RETRY_MAX", 3))


def _build_client() -> ClobClient:
    creds = ApiCreds(
        api_key=config.POLY_API_KEY,
        api_secret=config.POLY_API_SECRET,
        api_passphrase=config.POLY_API_PASSPHRASE,
    )
    return ClobClient(
        host=config.CLOB_HOST,
        chain_id=POLYGON,
        key=config.POLY_PRIVATE_KEY,
        creds=creds,
    )


def _with_backoff(fn, *args, **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff on Exception."""
    for attempt in range(RETRY_MAX):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            wait = 2 ** attempt * 2          # 2s, 4s, 8s
            if attempt < RETRY_MAX - 1:
                log.warning(f"API error ({e}), retry {attempt+1}/{RETRY_MAX} in {wait}s")
                time.sleep(wait)
            else:
                raise


class Executor:
    def __init__(self):
        self._client: Optional[ClobClient] = None

    def _c(self) -> ClobClient:
        if self._client is None:
            self._client = _build_client()
        return self._client

    # ── Order placement ───────────────────────────────────────────────────────
    def place_limit(
        self,
        token_id: str,
        side: str,
        price: float,
        size_usdc: float,
        dry_run: bool = False,   # FIX: was True — default True silently blocked all live orders
    ) -> dict:
        """
        Place a GTC limit order.  Returns order response dict.
        In dry_run mode: logs only, returns stub with dry_run=True.
        Live/dry is controlled by config.DRY_RUN; this param allows
        per-call override (e.g. tests).
        """
        if side == "YES":
            shares = round(size_usdc / price, 2)
        else:
            shares = round(size_usdc / (1 - price), 2)
            price  = round(1 - price, 4)     # NO token price

        if dry_run or config.DRY_RUN:
            log.info(
                f"[DRY RUN] {side} {shares:.2f}sh @ {price:.4f}"
                f" | token={token_id[:16]}"
            )
            return {"dry_run": True, "side": side, "price": price,
                    "shares": shares, "size_usdc": size_usdc,
                    "orderID": f"dry_{int(time.time())}"}

        order_args = OrderArgs(
            token_id=token_id, price=price, size=shares,
            side=side, order_type=OrderType.GTC
        )
        try:
            resp = _with_backoff(self._c().create_and_post_order, order_args)
            log.info(
                f"[ORDER] id={resp.get('orderID')} {side}@{price} sh={shares:.2f}"
            )
            return resp
        except Exception as e:
            log.error(f"[ORDER FAILED after retries] {e}")
            return {"error": str(e)}

    # ── Fill verification ─────────────────────────────────────────────────────
    def verify_fill(self, order_id: str, placed_at: int) -> str:
        """
        Poll the CLOB until the order is FILLED, CANCELLED, or EXPIRED.
        Returns one of: 'filled' | 'cancelled' | 'expired' | 'timeout' | 'dry_run'

        Cancels automatically if ORDER_FILL_TIMEOUT seconds pass without fill.
        Polls every 15s.
        """
        if config.DRY_RUN or order_id.startswith("dry_"):
            return "dry_run"

        deadline = placed_at + ORDER_FILL_TIMEOUT
        while time.time() < deadline:
            try:
                status = _with_backoff(self._c().get_order, order_id)
                state  = (status or {}).get("status", "").upper()
                log.debug(f"[FILL POLL] order={order_id[:16]} status={state}")
                if state == "MATCHED":    return "filled"
                if state in ("CANCELLED", "EXPIRED"): return state.lower()
            except Exception as e:
                log.warning(f"[FILL POLL ERROR] {e}")
            time.sleep(15)

        # Timeout — cancel the stale order
        log.warning(
            f"[STALE ORDER] {order_id[:16]} unfilled after {ORDER_FILL_TIMEOUT}s — cancelling"
        )
        self.cancel_order(order_id)
        return "timeout"

    # ── Cancel ────────────────────────────────────────────────────────────────
    def cancel_order(self, order_id: str) -> dict:
        if config.DRY_RUN:
            log.info(f"[DRY RUN] cancel {order_id}")
            return {"dry_run": True}
        try:
            return _with_backoff(self._c().cancel, order_id)
        except Exception as e:
            log.error(f"[CANCEL FAILED] {e}")
            return {"error": str(e)}

    # ── Reconcile on startup ──────────────────────────────────────────────────
    def reconcile_open_orders(self, state: dict) -> dict:
        """
        P1: On agent startup, fetch real open orders from CLOB and cross-check
        with state["open_orders"].  Remove any stale order references.
        Returns cleaned open_orders dict.
        """
        if config.DRY_RUN:
            return state.get("open_orders", {})

        try:
            live = _with_backoff(self._c().get_orders) or []
            live_ids = {o.get("id") for o in live}
            saved   = state.get("open_orders", {})
            stale   = [oid for oid in saved if oid not in live_ids]
            for oid in stale:
                log.warning(f"[RECONCILE] Removing stale order ref {oid[:16]}")
                del saved[oid]
            log.info(f"[RECONCILE] live={len(live_ids)} saved={len(saved)} stale={len(stale)}")
            return saved
        except Exception as e:
            log.error(f"[RECONCILE FAILED] {e}")
            return state.get("open_orders", {})
