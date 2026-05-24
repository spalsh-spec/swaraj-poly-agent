"""scanner.py — fetch Polymarket markets + price history, run signal pipeline."""
import asyncio, time, math
import aiohttp
from . import config
from .signal import evaluate

HEADERS = {"User-Agent": "Mozilla/5.0 (swaraj-poly-agent/1.0)"}

GAMMA  = config.GAMMA_API
CLOB   = config.CLOB_HOST


async def _get(session: aiohttp.ClientSession, url: str, params=None) -> dict | list:
    async with session.get(url, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
        r.raise_for_status()
        return await r.json()


async def fetch_active_markets(session: aiohttp.ClientSession, limit: int = 200) -> list[dict]:
    """Pull active markets from Gamma API, filter by volume."""
    raw = await _get(session, f"{GAMMA}/markets", params={
        "active": "true", "closed": "false",
        "volume_num_min": config.MIN_VOLUME,
        "limit": limit,
    })
    markets = raw if isinstance(raw, list) else raw.get("markets", [])
    return markets


async def fetch_price_history(session: aiohttp.ClientSession, token_id: str, fidelity: int = 60) -> list[float]:
    """Return list of YES-token prices from CLOB price history endpoint."""
    try:
        data = await _get(session, f"{CLOB}/prices-history", params={
            "market": token_id,
            "interval": "1d",
            "fidelity": fidelity,
        })
        history = data.get("history", [])
        return [float(p["p"]) for p in history if "p" in p]
    except Exception:
        return []


async def scan_markets() -> list[dict]:
    """
    Full scan: fetch markets → price history → signal evaluation.
    Returns list of signal dicts with market metadata attached.
    """
    signals = []
    async with aiohttp.ClientSession() as session:
        markets = await fetch_active_markets(session)
        tasks = []
        for m in markets:
            clob_ids = m.get("clobTokenIds") or []
            if not clob_ids:
                continue
            token_id = clob_ids[0]
            tasks.append(_analyze_market(session, m, token_id))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict):
                signals.append(r)
    # sort by kelly descending
    signals.sort(key=lambda x: x.get("best_kelly", 0), reverse=True)
    return signals


async def _analyze_market(session, market: dict, token_id: str) -> dict | None:
    prices = await fetch_price_history(session, token_id)
    if len(prices) < 32:
        return None
    current_price = prices[-1]
    if current_price <= 0.001 or current_price >= 0.999:
        return None
    sig = evaluate(prices, current_price)
    if sig is None:
        return None
    if sig["best_kelly"] < config.MIN_KELLY:
        return None
    if sig["H"] < config.MIN_HURST:
        return None
    return {
        **sig,
        "market_id":    market.get("id", ""),
        "condition_id": market.get("conditionId", ""),
        "token_id":     token_id,
        "question":     market.get("question", "")[:120],
        "volume":       float(market.get("volume", 0)),
        "end_date":     market.get("endDate", ""),
        "clob_ids":     market.get("clobTokenIds", []),
        "scanned_at":   int(time.time()),
    }
