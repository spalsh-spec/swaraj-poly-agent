#!/usr/bin/env python3
"""backtest.py — Simulate Swaraj trades from signals_log.csv.

Usage:
    python backtest.py [--csv dashboard/signals_log.csv] [--bankroll 100]

Simulation model:
    - Read every signal from CSV
    - Apply half-Kelly sizing (capped at MAX_SINGLE_BET)
    - Assume p_true is the "true" probability (our estimate)
    - Simulate binary outcome: market resolves YES with probability p_true
    - P&L: if YES bet fills at p_market → pnl = size/p_market - size (if resolved YES)
            if NO bet fills at (1-p_market) → pnl = size/(1-p_market) - size (if resolved NO)
    - Run Monte Carlo over N_SIM trials for confidence interval

WARNING: This is a simulation. Past signal quality does not guarantee future returns.
         The simulation assumes p_true is unbiased — which is an optimistic assumption.
"""
from __future__ import annotations
import csv, argparse, random, math, os
from pathlib import Path

SIGNAL_LOG = Path("dashboard/signals_log.csv")
N_SIM      = 1000
MAX_SINGLE = 0.10   # max 10% of bankroll per trade


def load_signals(path: Path) -> list[dict]:
    if not path.exists():
        print(f"No signal log at {path}. Run the agent first to collect signals.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def simulate_once(signals: list[dict], bankroll: float, seed: int) -> dict:
    rng = random.Random(seed)
    capital = bankroll
    trades, wins, losses = 0, 0, 0
    pnl_curve = [capital]

    for sig in signals:
        try:
            p_market  = float(sig.get("p_market", 0) or 0)
            p_true    = float(sig.get("p_true", 0) or 0)
            best_kelly = float(sig.get("best_kelly", 0) or 0)
            side      = sig.get("side", "YES")
        except (ValueError, TypeError):
            continue

        if best_kelly < 0.02 or p_market <= 0 or p_market >= 1:
            continue

        # Size: half-Kelly, capped
        bet = min(best_kelly * capital, MAX_SINGLE * capital)
        if bet < 0.50:
            continue

        trades += 1

        # Simulate outcome
        resolved_yes = rng.random() < p_true

        if side == "YES":
            if resolved_yes:
                # Win: bought at p_market, resolves to 1.0
                pnl = bet * (1.0 / p_market - 1)
                wins += 1
            else:
                pnl = -bet
                losses += 1
        else:  # NO
            if not resolved_yes:
                pnl = bet * (1.0 / (1 - p_market) - 1)
                wins += 1
            else:
                pnl = -bet
                losses += 1

        capital = max(0, capital + pnl)
        pnl_curve.append(capital)

    return {
        "final_capital": round(capital, 4),
        "pnl":           round(capital - bankroll, 4),
        "pnl_pct":       round((capital / bankroll - 1) * 100, 2),
        "trades":        trades,
        "wins":          wins,
        "losses":        losses,
        "win_rate":      round(wins / trades * 100, 1) if trades else 0,
        "pnl_curve":     pnl_curve,
    }


def run_backtest(csv_path: Path, bankroll: float):
    signals = load_signals(csv_path)
    if not signals:
        return

    print(f"\n{'═'*56}")
    print(f"  Swaraj Backtest — {len(signals)} signals, ${bankroll:.2f} bankroll")
    print(f"{'═'*56}")

    # Single deterministic run (seed=42)
    det = simulate_once(signals, bankroll, seed=42)
    print(f"\n  Deterministic run (seed=42):")
    print(f"    Trades executed : {det['trades']}")
    print(f"    Win rate        : {det['win_rate']}%")
    print(f"    P&L             : ${det['pnl']:+.2f}  ({det['pnl_pct']:+.1f}%)")
    print(f"    Final capital   : ${det['final_capital']:.2f}")

    # Monte Carlo
    print(f"\n  Monte Carlo ({N_SIM} simulations):")
    results = [simulate_once(signals, bankroll, seed=i) for i in range(N_SIM)]
    pnls    = sorted(r["pnl"] for r in results)
    avg_pnl = sum(pnls) / len(pnls)
    win_sim = sum(1 for p in pnls if p > 0)

    p5  = pnls[int(0.05 * N_SIM)]
    p50 = pnls[int(0.50 * N_SIM)]
    p95 = pnls[int(0.95 * N_SIM)]

    print(f"    Profitable runs : {win_sim/N_SIM*100:.0f}% of {N_SIM}")
    print(f"    Median P&L      : ${p50:+.2f}")
    print(f"    5th percentile  : ${p5:+.2f}  (worst case 95% of the time)")
    print(f"    95th percentile : ${p95:+.2f}  (best case 95% of the time)")
    print(f"    Mean P&L        : ${avg_pnl:+.2f}")

    print(f"\n  Signal quality summary:")
    hs     = [float(s["H"]) for s in signals if s.get("H")]
    kellys = [float(s["best_kelly"]) for s in signals if s.get("best_kelly")]
    if hs:
        print(f"    Avg Hurst H     : {sum(hs)/len(hs):.3f}  (max {max(hs):.3f})")
    if kellys:
        print(f"    Avg Kelly       : {sum(kellys)/len(kellys):.3f}  (max {max(kellys):.3f})")

    regimes = [s.get("regime","") for s in signals]
    print(f"    PERSISTENT sigs : {regimes.count('PERSISTENT')}/{len(regimes)}")

    print(f"\n{'─'*56}")
    print(f"  ⚠  Simulation only. p_true is our estimate, not ground truth.")
    print(f"     Real returns will differ. Never risk capital you can't lose.")
    print(f"{'═'*56}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Swaraj signal backtest")
    parser.add_argument("--csv", default=str(SIGNAL_LOG), help="Path to signals_log.csv")
    parser.add_argument("--bankroll", type=float, default=100.0, help="Starting bankroll USDC")
    args = parser.parse_args()
    run_backtest(Path(args.csv), args.bankroll)
