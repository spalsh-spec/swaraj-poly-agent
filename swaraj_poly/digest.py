"""digest.py — daily HTML email report for Swaraj positions and P&L.

Usage (standalone):
    python -m swaraj_poly.digest

Or import and call:
    from swaraj_poly.digest import send_digest
    send_digest(state)

Config via .env:
    DIGEST_EMAIL_TO   = you@gmail.com
    DIGEST_EMAIL_FROM = swaraj@yourdomain.com
    SMTP_HOST         = smtp.gmail.com
    SMTP_PORT         = 587
    SMTP_USER         = swaraj@yourdomain.com
    SMTP_PASSWORD     = <app-password>

If SMTP creds are absent, digest is written to dashboard/digest_YYYYMMDD.html.
"""
from __future__ import annotations
import os, json, smtplib, logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config
from .tracker import load_state, STATE_FILE

log = logging.getLogger("digest")

DIGEST_EMAIL_TO   = os.getenv("DIGEST_EMAIL_TO", "")
DIGEST_EMAIL_FROM = os.getenv("DIGEST_EMAIL_FROM", "swaraj-agent@localhost")
SMTP_HOST         = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER         = os.getenv("SMTP_USER", "")
SMTP_PASSWORD     = os.getenv("SMTP_PASSWORD", "")

_DASHBOARD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "dashboard", "live.json"
)


# ── HTML builder ──────────────────────────────────────────────────────────────

_CSS = """
body{font-family:system-ui,sans-serif;background:#0d0d0d;color:#e0e0e0;margin:0;padding:24px}
h1{font-size:1.4rem;color:#f0c040;margin-bottom:4px}
.sub{font-size:.85rem;color:#888;margin-bottom:24px}
.card{background:#1a1a1a;border-radius:8px;padding:16px;margin-bottom:16px}
.card h2{font-size:1rem;color:#a0a0a0;margin:0 0 12px}
.metric{display:inline-block;margin-right:24px;margin-bottom:8px}
.metric .label{font-size:.75rem;color:#666;text-transform:uppercase;letter-spacing:.06em}
.metric .val{font-size:1.6rem;font-weight:700;color:#f0f0f0}
.metric .val.green{color:#4ade80}
.metric .val.red{color:#f87171}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;color:#555;border-bottom:1px solid #2a2a2a;padding:6px 8px}
td{padding:6px 8px;border-bottom:1px solid #1f1f1f}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600}
.badge.yes{background:#14532d;color:#4ade80}
.badge.no{background:#450a0a;color:#f87171}
.footer{font-size:.75rem;color:#444;margin-top:32px}
"""


def _pnl_class(v: float) -> str:
    return "green" if v >= 0 else "red"


def _fmt_pnl(v: float) -> str:
    return f"${v:+.2f}"


def _build_html(state: dict, signals: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    daily   = state.get("daily_pnl", 0)
    total   = state.get("total_pnl", 0)
    trades  = state.get("trades", [])
    positions = state.get("positions", {})
    dry_tag = " [DRY RUN]" if config.DRY_RUN else ""

    # ── KPI cards ─────────────────────────────────────────────────────────────
    kpis = f"""
    <div class="card">
      <h2>Today's P&amp;L{dry_tag}</h2>
      <div class="metric"><div class="label">Daily P&amp;L</div>
        <div class="val {_pnl_class(daily)}">{_fmt_pnl(daily)}</div></div>
      <div class="metric"><div class="label">Total P&amp;L</div>
        <div class="val {_pnl_class(total)}">{_fmt_pnl(total)}</div></div>
      <div class="metric"><div class="label">Open Positions</div>
        <div class="val">{len(positions)}</div></div>
      <div class="metric"><div class="label">Closed Trades</div>
        <div class="val">{len(trades)}</div></div>
    </div>"""

    # ── Open positions table ──────────────────────────────────────────────────
    pos_rows = ""
    for tok, p in positions.items():
        badge_cls = "yes" if p.get("side") == "YES" else "no"
        pos_rows += (
            f"<tr><td>{p.get('question','')[:70]}</td>"
            f"<td><span class='badge {badge_cls}'>{p.get('side','')}</span></td>"
            f"<td>${p.get('size_usdc',0):.2f}</td>"
            f"<td>{p.get('entry_price',0):.3f}</td>"
            f"<td>{p.get('H',0):.3f}</td>"
            f"<td>{p.get('regime','')}</td></tr>"
        )
    pos_section = f"""
    <div class="card">
      <h2>Open Positions ({len(positions)})</h2>
      <table>
        <tr><th>Question</th><th>Side</th><th>Size</th>
            <th>Entry</th><th>Hurst H</th><th>Regime</th></tr>
        {pos_rows or '<tr><td colspan="6" style="color:#555">No open positions</td></tr>'}
      </table>
    </div>"""

    # ── Top signals ───────────────────────────────────────────────────────────
    sig_rows = ""
    for s in signals[:10]:
        badge_cls = "yes" if s.get("side") == "YES" else "no"
        sig_rows += (
            f"<tr><td>{s.get('question','')[:70]}</td>"
            f"<td><span class='badge {badge_cls}'>{s.get('side','')}</span></td>"
            f"<td>{s.get('H',0):.3f}</td>"
            f"<td>{s.get('p_market',0):.3f}</td>"
            f"<td>{s.get('p_true',0):.3f}</td>"
            f"<td>{s.get('best_kelly',0):.3f}</td></tr>"
        )
    sig_section = f"""
    <div class="card">
      <h2>Top Signals (last scan)</h2>
      <table>
        <tr><th>Question</th><th>Side</th><th>H</th>
            <th>Mkt Price</th><th>True P</th><th>Kelly</th></tr>
        {sig_rows or '<tr><td colspan="6" style="color:#555">No signals yet</td></tr>'}
      </table>
    </div>"""

    # ── Recent closed trades ──────────────────────────────────────────────────
    trade_rows = ""
    for t in reversed(trades[-10:]):
        pnl_v = t.get("pnl", 0)
        ts = datetime.fromtimestamp(t.get("ts", 0), tz=timezone.utc).strftime("%m-%d %H:%M")
        trade_rows += (
            f"<tr><td>{ts}</td>"
            f"<td>{t.get('question','')[:60]}</td>"
            f"<td class='{_pnl_class(pnl_v)}'>{_fmt_pnl(pnl_v)}</td></tr>"
        )
    trades_section = f"""
    <div class="card">
      <h2>Recent Closed Trades</h2>
      <table>
        <tr><th>Time</th><th>Question</th><th>P&amp;L</th></tr>
        {trade_rows or '<tr><td colspan="3" style="color:#555">No closed trades</td></tr>'}
      </table>
    </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Swaraj Daily Digest — {now}</title>
<style>{_CSS}</style></head><body>
<h1>⚡ Swaraj Daily Digest</h1>
<div class="sub">{now}{dry_tag}</div>
{kpis}{pos_section}{sig_section}{trades_section}
<div class="footer">
  Bankroll: ${config.BANKROLL_USDC:.2f} USDC |
  MIN_HURST={config.MIN_HURST} | MIN_KELLY={config.MIN_KELLY} |
  Swaraj Poly Agent
</div>
</body></html>"""


# ── Send / save ───────────────────────────────────────────────────────────────

def _load_live_signals() -> list:
    """Read last scan signals from dashboard/live.json if available."""
    try:
        with open(_DASHBOARD_PATH) as f:
            data = json.load(f)
        return data.get("signals", [])
    except Exception:
        return []


def send_digest(state: dict | None = None):
    """Build and dispatch (email or file) the daily digest."""
    if state is None:
        state = load_state()
    signals = _load_live_signals()
    html    = _build_html(state, signals)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    # ── Try SMTP ──────────────────────────────────────────────────────────────
    if DIGEST_EMAIL_TO and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Swaraj Digest {date_str} | PnL {state.get('daily_pnl',0):+.2f}"
            msg["From"]    = DIGEST_EMAIL_FROM
            msg["To"]      = DIGEST_EMAIL_TO
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(DIGEST_EMAIL_FROM, [DIGEST_EMAIL_TO], msg.as_string())

            log.info(f"[DIGEST] Email sent → {DIGEST_EMAIL_TO}")
            return
        except Exception as e:
            log.warning(f"[DIGEST] SMTP failed ({e}) — falling back to file")

    # ── Fallback: write HTML to dashboard/ ───────────────────────────────────
    out_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"digest_{date_str}.html")
    with open(out_path, "w") as f:
        f.write(html)
    log.info(f"[DIGEST] Written → {out_path}")
    print(f"Digest saved: {out_path}")


# ── CLI entry ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    send_digest()
