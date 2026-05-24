"""executor.py — place/cancel orders via py-clob-client (CLOB API)."""
import logging
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.constants import POLYGON

from . import config

log = logging.getLogger("executor")


def _build_client() -> ClobClient:
    """Instantiate the CLOB client with L2 API auth."""
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
        side: str,            # "YES" or "NO"
        price: float,         # limit price in [0,1]
        size_usdc: float,     # dollar size
        dry_run: bool = True,
    ) -> dict:
        """
        Place a limit order. In dry_run mode, log only — no real order sent.
        Returns simulated or real order response dict.
        """
        # Polymarket CLOB uses shares (not dollars):
        # shares = size_usdc / price  (for YES), or size_usdc / (1-price) for NO
        if side == "YES":
            shares = round(size_usdc / price, 2)
        else:
            shares = round(size_usdc / (1 - price), 2)
            price  = round(1 - price, 4)   # NO token price

        if dry_run or config.DRY_RUN:
            log.info(f"[DRY RUN] {side} {shares:.2f} shares @ {price:.4f} | token={token_id[:16]}")
            return {"dry_run": True, "side": side, "price": price,
                    "shares": shares, "size_usdc": size_usdc}

        order_args = OrderArgs(token_id=token_id, price=price, size=shares,
                               side=side, order_type=OrderType.GTC)
        try:
            resp = self._c().create_and_post_order(order_args)
            log.info(f"[ORDER PLACED] id={resp.get('orderID')} {side}@{price} shares={shares}")
            return resp
        except Exception as e:
            log.error(f"[ORDER FAILED] {e}")
            return {"error": str(e)}

    def cancel_order(self, order_id: str) -> dict:
        if config.DRY_RUN:
            log.info(f"[DRY RUN] cancel {order_id}")
            return {"dry_run": True}
        try:
            return self._c().cancel(order_id)
        except Exception as e:
            log.error(f"[CANCEL FAILED] {e}")
            return {"error": str(e)}
