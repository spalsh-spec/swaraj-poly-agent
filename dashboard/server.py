"""dashboard/server.py — Minimal localhost dashboard for Swaraj.

Run:  python dashboard/server.py
Open: http://localhost:8765

Serves a single-page app that polls dashboard/live.json every 15s
and renders KPIs + positions + signals in dark mode.
No external dependencies beyond Python stdlib.
"""
import http.server, json, os, urllib.parse
from datetime import datetime, timezone

PORT = int(os.getenv("DASHBOARD_PORT", "8765"))
LIVE_JSON = os.path.join(os.path.dirname(__file__), "live.json")

_HTML = r"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>⚡ Swaraj Live</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#ddd;font-family:system-ui,sans-serif;padding:20px}
h1{color:#f0c040;font-size:1.4rem;margin-bottom:4px}
.sub{color:#555;font-size:.8rem;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}
.kpi{background:#141414;border-radius:8px;padding:14px}
.kpi .label{font-size:.7rem;color:#555;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px}
.kpi .val{font-size:1.7rem;font-weight:700}
.green{color:#4ade80}.red{color:#f87171}.dim{color:#888}
section{background:#141414;border-radius:8px;padding:16px;margin-bottom:16px}
section h2{font-size:.9rem;color:#666;margin-bottom:12px;text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th{text-align:left;color:#444;padding:5px 8px;border-bottom:1px solid #1e1e1e}
td{padding:5px 8px;border-bottom:1px solid #181818}
.badge{display:inline-block;padding:1px 7px;border-radius:3px;font-size:.7rem;font-weight:700}
.yes{background:#14532d;color:#4ade80}.no{background:#450a0a;color:#f87171}
.dry{display:inline-block;background:#2d2700;color:#f0c040;padding:2px 8px;border-radius:4px;font-size:.75rem}
#status{font-size:.75rem;color:#333;margin-top:24px}
</style>
</head>
<body>
<h1>⚡ Swaraj Poly Agent</h1>
<div class="sub" id="ts">Loading…</div>
<div id="dry-badge"></div>
<br>
<div class="grid" id="kpis"></div>
<section><h2>Open Positions</h2><div id="positions"></div></section>
<section><h2>Top Signals (last scan)</h2><div id="signals"></div></section>
<div id="status">Auto-refreshing every 15s</div>

<script>
async function load(){
  try{
    const r=await fetch('/data');
    if(!r.ok)throw new Error(r.status);
    const d=await r.json();
    render(d);
  }catch(e){
    document.getElementById('status').textContent='⚠ '+e;
  }
}

function pnlClass(v){return v>=0?'green':'red'}
function fmt(v){return(v>=0?'+':'')+v.toFixed(2)}

function render(d){
  document.getElementById('ts').textContent=d.updated||'—';
  document.getElementById('dry-badge').innerHTML=
    d.dry_run?'<span class="dry">DRY RUN</span>':'';

  const risk=d.risk||{};
  document.getElementById('kpis').innerHTML=`
    <div class="kpi"><div class="label">Daily P&L</div>
      <div class="val ${pnlClass(d.daily_pnl||0)}">$${fmt(d.daily_pnl||0)}</div></div>
    <div class="kpi"><div class="label">Total P&L</div>
      <div class="val ${pnlClass(d.total_pnl||0)}">$${fmt(d.total_pnl||0)}</div></div>
    <div class="kpi"><div class="label">Bankroll</div>
      <div class="val dim">$${(d.bankroll||0).toFixed(2)}</div></div>
    <div class="kpi"><div class="label">Deployed</div>
      <div class="val dim">$${(risk.deployed_usdc||0).toFixed(2)}</div></div>
    <div class="kpi"><div class="label">Positions</div>
      <div class="val">${risk.open_positions||0}</div></div>
    <div class="kpi"><div class="label">Agent</div>
      <div class="val ${risk.paused?'red':'green'}">${risk.paused?'PAUSED':'LIVE'}</div></div>
  `;

  const pos=d.positions||[];
  document.getElementById('positions').innerHTML=pos.length?`
    <table><tr><th>Question</th><th>Side</th><th>Size</th><th>Entry</th><th>H</th></tr>
    ${pos.map(p=>`<tr>
      <td>${(p.question||'').slice(0,70)}</td>
      <td><span class="badge ${(p.side||'').toLowerCase()}">${p.side||''}</span></td>
      <td>$${(p.size_usdc||0).toFixed(2)}</td>
      <td>${(p.entry_price||0).toFixed(3)}</td>
      <td>${(p.H||0).toFixed(3)}</td>
    </tr>`).join('')}
    </table>`:'<span style="color:#333">No open positions</span>';

  const sigs=d.signals||[];
  document.getElementById('signals').innerHTML=sigs.length?`
    <table><tr><th>Question</th><th>Side</th><th>H</th><th>Mkt</th><th>True P</th><th>Kelly</th></tr>
    ${sigs.slice(0,10).map(s=>`<tr>
      <td>${(s.question||'').slice(0,70)}</td>
      <td><span class="badge ${(s.side||'').toLowerCase()}">${s.side||''}</span></td>
      <td>${(s.H||0).toFixed(3)}</td>
      <td>${(s.p_market||0).toFixed(3)}</td>
      <td>${(s.p_true||0).toFixed(3)}</td>
      <td>${(s.best_kelly||0).toFixed(3)}</td>
    </tr>`).join('')}
    </table>`:'<span style="color:#333">No signals yet</span>';
}

load();
setInterval(load,15000);
</script>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass   # suppress access log noise

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/data":
            try:
                with open(LIVE_JSON) as f:
                    body = f.read().encode()
                self._respond(200, "application/json", body)
            except FileNotFoundError:
                self._respond(200, "application/json", b"{}")
        else:
            self._respond(200, "text/html; charset=utf-8", _HTML.encode())

    def _respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    import sys
    print(f"⚡ Swaraj dashboard → http://localhost:{PORT}")
    with http.server.HTTPServer(("127.0.0.1", PORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard stopped.")
            sys.exit(0)
