"""Minimal zero-dependency web UI for the shopping agent.

Renders the pipeline's CustomerResponse as visual cards. Runs offline
(seeded search fixture); set SEARCHAPI_API_KEY for real Google Shopping.

    PYTHONPATH=src python examples/webui.py      # then open http://localhost:8765
"""

from __future__ import annotations

import html
import sys
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from shopping_agent.pipeline import run_shopping
from shopping_agent.schemas import PickTier, UserRequirements, Weights

PORT = 8765

_TIER = {
    PickTier.BEST_OVERALL: ("BEST OVERALL", "🥇", "overall"),
    PickTier.BEST_VALUE: ("BEST VALUE", "💰", "value"),
    PickTier.BEST_UPGRADE: ("BEST UPGRADE", "⭐", "upgrade"),
}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shopping Agent</title>
<style>
  :root{{--bg:#0f1216;--surface:#1a1f26;--surface2:#232a33;--ink:#eef1f4;
    --soft:#9aa4b0;--line:#2c343d;--accent:#49b6c6;--overall:#e0b341;
    --value:#4cc98a;--upgrade:#a98bff;--shadow:0 6px 24px rgba(0,0,0,.35)}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);
    font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5}}
  .wrap{{max-width:820px;margin:0 auto;padding:32px 20px 60px}}
  h1{{font-size:1.7rem;margin:0 0 4px;letter-spacing:-.02em}}
  .tag{{color:var(--soft);font-size:.9rem;margin:0 0 24px}}
  form{{display:grid;grid-template-columns:1fr 140px;gap:12px;
    background:var(--surface);border:1px solid var(--line);border-radius:14px;
    padding:16px;box-shadow:var(--shadow);margin-bottom:8px}}
  form .full{{grid-column:1/-1}}
  label{{display:block;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;
    color:var(--soft);margin-bottom:4px}}
  input{{width:100%;background:var(--surface2);border:1px solid var(--line);
    border-radius:8px;color:var(--ink);padding:10px 12px;font-size:.95rem;font-family:inherit}}
  input:focus{{outline:2px solid var(--accent);outline-offset:1px}}
  button{{grid-column:1/-1;background:var(--accent);color:#04222a;border:0;
    border-radius:9px;padding:12px;font-size:1rem;font-weight:600;cursor:pointer;font-family:inherit}}
  button:hover{{filter:brightness(1.08)}}
  .headline{{margin:28px 0 14px;font-size:.85rem;text-transform:uppercase;
    letter-spacing:.1em;color:var(--soft)}}
  .card{{display:grid;grid-template-columns:96px 1fr;gap:16px;background:var(--surface);
    border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:14px;
    box-shadow:var(--shadow);position:relative;overflow:hidden}}
  .card::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent)}}
  .card.overall::before{{background:var(--overall)}}
  .card.value::before{{background:var(--value)}}
  .card.upgrade::before{{background:var(--upgrade)}}
  .thumb{{width:96px;height:96px;border-radius:10px;background:var(--surface2);
    display:grid;place-items:center;font-size:2rem;overflow:hidden}}
  .thumb img{{width:100%;height:100%;object-fit:cover}}
  .badge{{display:inline-block;font-size:.68rem;font-weight:700;letter-spacing:.06em;
    padding:3px 9px;border-radius:6px;margin-bottom:6px}}
  .badge.overall{{background:rgba(224,179,65,.16);color:var(--overall)}}
  .badge.value{{background:rgba(76,201,138,.16);color:var(--value)}}
  .badge.upgrade{{background:rgba(169,139,255,.16);color:var(--upgrade)}}
  .title{{font-weight:600;font-size:1.03rem;margin:0 0 2px}}
  .price{{font-size:1.05rem;font-weight:700}}
  .metaline{{color:var(--soft);font-size:.86rem;margin:2px 0 6px}}
  .match{{font-family:"IBM Plex Mono",monospace;font-size:.8rem;color:var(--accent);
    font-weight:600}}
  .reason{{font-size:.9rem;margin:6px 0}}
  .facts{{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}}
  .fact{{font-size:.8rem;background:var(--surface2);border:1px solid var(--line);
    border-radius:6px;padding:3px 8px;color:var(--soft)}}
  .cta{{display:inline-block;margin-top:6px;background:var(--surface2);
    border:1px solid var(--accent);color:var(--accent);text-decoration:none;
    border-radius:8px;padding:8px 12px;font-size:.85rem;font-weight:600}}
  .cta:hover{{background:var(--accent);color:#04222a}}
  .ctanote{{font-size:.78rem;color:var(--soft);margin-top:4px}}
  .footer{{margin-top:22px;color:var(--soft);font-size:.85rem;text-align:center}}
  @media(max-width:560px){{form{{grid-template-columns:1fr}}.card{{grid-template-columns:64px 1fr}}
    .thumb{{width:64px;height:64px}}}}
  @font-face{{font-family:"IBM Plex Sans";src:local("IBM Plex Sans")}}
</style></head><body><div class="wrap">
<h1>🛍 Shopping Agent</h1>
<p class="tag">Search &rarr; recommend &rarr; pickup &middot; after-sales &middot; checkout. Offline demo.</p>
<form method="get" action="/">
  <div class="full"><label>What are you looking for?</label>
    <input name="q" value="{q}" placeholder="running shoes" autofocus></div>
  <div><label>Budget (SGD)</label><input name="budget" value="{budget}" placeholder="150"></div>
  <div><label>Preferences (comma-sep)</label><input name="prefs" value="{prefs}" placeholder="cushioned, lightweight"></div>
  <button type="submit">Find products</button>
</form>
{results}
<p class="footer">Nothing is ever ordered — you complete checkout yourself.</p>
</div></body></html>"""


def _card_html(card) -> str:
    tier = _TIER.get(card.tier)
    cls, badge = "", ""
    if tier:
        label, emoji, cls = tier
        badge = f'<span class="badge {cls}">{emoji} {html.escape(label)}</span>'
    img = ""
    if card.image_url:
        img = (f'<img src="{html.escape(card.image_url)}" alt="" '
               f'onerror="this.style.display=\'none\';this.parentNode.textContent=\'🛍\'">')
    rating = f' &middot; {card.rating}★' if card.rating is not None else ""
    match = ""
    if card.match_pct is not None:
        match = f'<div class="match">{card.match_pct}% {html.escape(card.match_label)}</div>'
    facts = []
    if card.availability:
        facts.append(f'<span class="fact">🚚 {html.escape(card.availability)}</span>')
    if card.after_sales:
        facts.append(f'<span class="fact">📋 {html.escape(card.after_sales)}</span>')
    facts_html = f'<div class="facts">{"".join(facts)}</div>' if facts else ""
    cta = ""
    if card.checkout_url:
        cta = (f'<a class="cta" href="{html.escape(card.checkout_url)}" target="_blank" '
               f'rel="noopener">Checkout →</a>'
               f'<div class="ctanote">{html.escape(card.checkout_note)}</div>')
    return f"""<div class="card {cls}">
      <div class="thumb">{img or "🛍"}</div>
      <div>{badge}
        <div class="title">{html.escape(card.title)}</div>
        <div class="price">{html.escape(card.price)}<span class="metaline">{rating} &middot; {html.escape(card.platform)}</span></div>
        {match}
        <div class="reason">{html.escape(card.reason)}</div>
        {facts_html}{cta}
      </div></div>"""


def _render_results(params) -> str:
    q = (params.get("q", [""])[0] or "").strip()
    if not q:
        return ""
    budget_raw = (params.get("budget", [""])[0] or "").strip()
    prefs = [p.strip() for p in (params.get("prefs", [""])[0] or "").split(",") if p.strip()]
    reqs = UserRequirements(
        product_query=q,
        budget=Decimal(budget_raw) if budget_raw else None,
        preferences=prefs,
        weights=Weights(price=0.2, speed=0.2, preference=0.6),
        max_results=3,
    )
    resp = run_shopping(reqs, session_id="webui")
    if not resp.cards:
        return f'<p class="headline">{html.escape(resp.headline)}</p>'
    cards = "".join(_card_html(c) for c in resp.cards)
    return f'<p class="headline">{html.escape(resp.headline)}</p>{cards}'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        try:
            results = _render_results(params)
        except Exception as exc:  # keep the UI alive on bad input
            results = f'<p class="headline">Error: {html.escape(str(exc))}</p>'
        body = PAGE.format(
            q=html.escape(params.get("q", [""])[0]),
            budget=html.escape(params.get("budget", [""])[0]),
            prefs=html.escape(params.get("prefs", [""])[0]),
            results=results,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet
        pass


if __name__ == "__main__":
    print(f"Shopping Agent UI  ->  http://localhost:{PORT}", flush=True)
    try:
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
