"""Muse web UI, wired to the integrated pipeline.

Adopts yanzhu's "Muse" visual identity, but the backend is the real
integration pipeline (search -> recommend -> pickup/service/cart -> customer
response) instead of the mock conversational graph. So the cards show real
search results, the curated 🥇/💰/⭐ tiers, delivery/after-sales, and genuine
checkout links.

Zero dependencies (Python standard library). Runs offline via the seeded
search fixture; set SEARCHAPI_API_KEY for real Google Shopping.

    python -m shopping_agent.ui            # then open http://127.0.0.1:8000
"""

from __future__ import annotations

import html
import sys
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from shopping_agent.pipeline import run_shopping
from shopping_agent.schemas import PickTier, UserRequirements, Weights

PORT = 8000

# tier -> (label, emoji, css-class)
_TIER = {
    PickTier.BEST_OVERALL: ("Best Overall", "🥇", "overall"),
    PickTier.BEST_VALUE: ("Best Value", "💰", "value"),
    PickTier.BEST_UPGRADE: ("Best Upgrade", "⭐", "upgrade"),
}

CSS = """
  :root{
    --ink:#242236;--muted:#77748c;--line:#ebe9f2;--purple:#6f52d9;
    --purple-dark:#5138b8;--lavender:#f1efff;--orange:#ff9b62;--green:#2ca879;
    --gold:#e0a341;--surface:#fff;--bg:#f7f7fb;
    font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0;color:var(--ink);background:var(--bg)}
  .layout{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
  /* sidebar */
  .sidebar{background:#29263c;color:#fff;padding:28px 20px;display:flex;flex-direction:column;gap:26px}
  .brand{display:flex;align-items:center;gap:11px;font-weight:800;letter-spacing:.02em}
  .brand-mark{width:34px;height:34px;border-radius:12px;display:grid;place-items:center;
    background:linear-gradient(135deg,#a78cff,#ff9b62);font-weight:900}
  .tagline{color:#b8b3cf;font-size:13px;line-height:1.6;margin:0}
  .steps{display:flex;flex-direction:column;gap:16px;margin:0;padding:0;list-style:none}
  .step{display:flex;gap:11px;font-size:13px}
  .step .n{width:22px;height:22px;flex:none;border-radius:50%;background:rgba(255,255,255,.1);
    display:grid;place-items:center;font-size:11px;font-weight:700;color:#d9d5ef}
  .step b{display:block;margin-bottom:1px}
  .step span{color:#a29dbd;font-size:12px}
  .status-box{margin-top:auto;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.1);
    border-radius:15px;padding:13px;font-size:12px;color:#c7c3d9}
  .status-dot{width:8px;height:8px;display:inline-block;border-radius:50%;background:var(--orange);margin-right:7px}
  /* main */
  .main{display:flex;flex-direction:column}
  .topbar{height:70px;padding:0 42px;display:flex;align-items:center;justify-content:space-between;
    border-bottom:1px solid var(--line);background:rgba(255,255,255,.75)}
  .topbar-title{font-size:13px;color:var(--muted)}
  .pill{border:1px solid var(--line);background:#fff;color:var(--muted);border-radius:999px;
    font-size:11px;padding:8px 12px}
  .content{padding:34px 42px 60px;max-width:1000px;width:100%}
  .eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--purple);font-size:11px;font-weight:800}
  .hero h1{font-size:2.4rem;line-height:1.08;margin:.4rem 0 .5rem;letter-spacing:-.02em}
  .hero p{margin:0 0 24px;color:var(--muted);max-width:540px;line-height:1.6}
  /* search form */
  form.search{background:var(--surface);border:1px solid var(--line);border-radius:22px;
    box-shadow:0 10px 35px rgba(48,40,88,.05);padding:20px;display:grid;
    grid-template-columns:1fr 150px;gap:14px;margin-bottom:8px}
  form.search .full{grid-column:1/-1}
  label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;
    color:var(--muted);font-weight:800;margin-bottom:6px}
  input{width:100%;border:1px solid #ddd9ee;border-radius:12px;padding:11px 13px;font-size:14px;
    color:var(--ink);font-family:inherit}
  input:focus{outline:0;border-color:var(--purple);box-shadow:0 0 0 3px rgba(111,82,217,.1)}
  button.go{grid-column:1/-1;border:0;background:var(--purple);color:#fff;border-radius:13px;
    padding:13px;font-size:15px;font-weight:700;cursor:pointer}
  button.go:hover{background:var(--purple-dark)}
  /* results */
  .results-head{margin:30px 0 16px;display:flex;align-items:baseline;gap:10px}
  .results-head h2{font-size:1.2rem;margin:0}
  .results-head span{color:var(--muted);font-size:12px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px}
  .product-card{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#fff;
    box-shadow:0 10px 35px rgba(48,40,88,.05);display:flex;flex-direction:column}
  .art{height:104px;padding:13px;display:flex;justify-content:space-between;align-items:flex-start;
    background:linear-gradient(135deg,#e9e4ff,#fff0e7)}
  .icon{width:52px;height:52px;display:grid;place-items:center;border-radius:15px;
    background:rgba(255,255,255,.7);font-size:26px}
  .platform{border-radius:999px;padding:5px 9px;background:rgba(255,255,255,.78);color:#726c86;
    font-size:10px;font-weight:700}
  .badge{align-self:flex-start;margin:-14px 0 0 13px;position:relative;z-index:1;font-size:11px;
    font-weight:800;padding:5px 10px;border-radius:999px;color:#fff}
  .badge.overall{background:var(--purple)}
  .badge.value{background:var(--green)}
  .badge.upgrade{background:var(--orange)}
  .pbody{padding:14px 15px 16px;display:flex;flex-direction:column;gap:7px;flex:1}
  .ptitle{font-weight:700;font-size:14px;line-height:1.35;margin:0}
  .price-row{display:flex;align-items:baseline;gap:8px}
  .price{font-size:1.15rem;font-weight:800}
  .rating{color:var(--muted);font-size:12px}
  .match{font-size:11px;font-weight:800;color:var(--purple);letter-spacing:.02em}
  .reason{font-size:12.5px;color:#5b586b;line-height:1.5}
  .facts{display:flex;flex-direction:column;gap:4px;margin-top:2px}
  .fact{font-size:11.5px;color:var(--muted)}
  .cart-button{margin-top:auto;border:0;border-radius:11px;background:var(--purple);color:#fff;
    padding:10px;font-size:12px;font-weight:700;cursor:pointer;text-decoration:none;text-align:center;display:block}
  .cart-button:hover{background:var(--purple-dark)}
  .cart-note{font-size:10.5px;color:var(--muted);margin-top:5px;line-height:1.4}
  .empty{background:#fff;border:1px solid var(--line);border-radius:18px;padding:28px;color:var(--muted)}
  .footer{margin-top:26px;color:var(--muted);font-size:12px}
  @media(max-width:820px){.layout{grid-template-columns:1fr}.sidebar{display:none}
    form.search{grid-template-columns:1fr}}
"""


def _page(query: str, budget: str, prefs: str, results: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Muse — Shopping Agent</title>"
        "<link rel=preconnect href='https://fonts.googleapis.com'>"
        "<link rel=stylesheet href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap'>"
        f"<style>{CSS}</style></head><body><div class=layout>"
        # sidebar
        "<aside class=sidebar>"
        "<div class=brand><span class=brand-mark>M</span> MUSE SHOP</div>"
        "<p class=tagline>A calmer way to find products that fit your needs — powered by the live pipeline.</p>"
        "<ol class=steps>"
        "<li class=step><span class=n>1</span><div><b>Tell us what you need</b><span>Product, budget, preferences.</span></div></li>"
        "<li class=step><span class=n>2</span><div><b>We search &amp; rank</b><span>Real results, scored to your priorities.</span></div></li>"
        "<li class=step><span class=n>3</span><div><b>Pickup, returns, checkout</b><span>Everything to decide and buy.</span></div></li>"
        "</ol>"
        "<div class=status-box><span class=status-dot></span>Offline demo · seeded search · no order is ever placed</div>"
        "</aside>"
        # main
        "<main class=main>"
        "<div class=topbar><span class=topbar-title>AI-powered product discovery</span>"
        "<span class=pill>Integrated pipeline · offline</span></div>"
        "<div class=content>"
        "<div class=hero><div class=eyebrow>Personal shopping, simplified</div>"
        "<h1>Find something you&rsquo;ll love.</h1>"
        "<p>Tell Muse what you&rsquo;re looking for. It searches, ranks to your priorities, and shows how to get each one.</p></div>"
        "<form class=search method=get action=/>"
        f"<div class=full><label>What are you looking for?</label><input name=q value=\"{query}\" placeholder='running shoes' autofocus></div>"
        f"<div><label>Budget (SGD)</label><input name=budget value=\"{budget}\" placeholder='150'></div>"
        f"<div><label>Preferences (comma-separated)</label><input name=prefs value=\"{prefs}\" placeholder='cushioned, lightweight'></div>"
        "<button class=go type=submit>Find products</button>"
        "</form>"
        f"{results}"
        "</div></main></div></body></html>"
    )


def _card(card) -> str:
    tier = _TIER.get(card.tier)
    badge = ""
    if tier:
        label, emoji, cls = tier
        badge = f"<div class='badge {cls}'>{emoji} {html.escape(label)}</div>"
    platform = html.escape(card.platform)
    rating = f"<span class=rating>{card.rating}★</span>" if card.rating is not None else ""
    match = ""
    if card.match_pct is not None:
        match = f"<div class=match>{card.match_pct}% {html.escape(card.match_label)}</div>"
    facts = []
    if card.availability:
        facts.append(f"<div class=fact>🚚 {html.escape(card.availability)}</div>")
    if card.after_sales:
        facts.append(f"<div class=fact>📋 {html.escape(card.after_sales)}</div>")
    facts_html = f"<div class=facts>{''.join(facts)}</div>" if facts else ""
    cta = ""
    if card.checkout_url:
        cta = (
            f"<a class=cart-button href=\"{html.escape(card.checkout_url)}\" target=_blank rel=noopener>Checkout &rarr;</a>"
            f"<div class=cart-note>{html.escape(card.checkout_note)}</div>"
        )
    return (
        "<div class=product-card>"
        f"<div class=art><div class=icon>🛍</div><span class=platform>{platform}</span></div>"
        f"{badge}"
        "<div class=pbody>"
        f"<p class=ptitle>{html.escape(card.title)}</p>"
        f"<div class=price-row><span class=price>{html.escape(card.price)}</span>{rating}</div>"
        f"{match}"
        f"<div class=reason>{html.escape(card.reason)}</div>"
        f"{facts_html}{cta}"
        "</div></div>"
    )


def _results(params) -> str:
    q = (params.get("q", [""])[0] or "").strip()
    if not q:
        return ""
    budget_raw = (params.get("budget", [""])[0] or "").strip()
    prefs = [p.strip() for p in (params.get("prefs", [""])[0] or "").split(",") if p.strip()]
    budget = None
    if budget_raw:
        try:
            budget = Decimal(budget_raw)
        except InvalidOperation:
            budget = None
    reqs = UserRequirements(
        product_query=q,
        budget=budget,
        preferences=prefs,
        weights=Weights(price=0.2, speed=0.2, preference=0.6),
        max_results=3,
    )
    resp = run_shopping(reqs, session_id="webui")
    if not resp.cards:
        return f"<div class=empty>{html.escape(resp.headline)}</div>"
    cards = "".join(_card(c) for c in resp.cards)
    return (
        f"<div class=results-head><h2>{html.escape(resp.headline)}</h2>"
        f"<span>{len(resp.cards)} picks · nothing ordered</span></div>"
        f"<div class=grid>{cards}</div>"
        f"<div class=footer>{html.escape(resp.footer)}</div>"
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        try:
            results = _results(params)
        except Exception as exc:  # keep the UI alive on bad input
            results = f"<div class=empty>Error: {html.escape(str(exc))}</div>"
        body = _page(
            html.escape(params.get("q", [""])[0]),
            html.escape(params.get("budget", [""])[0]),
            html.escape(params.get("prefs", [""])[0]),
            results,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet
        pass


def main() -> None:
    print(f"Muse UI  ->  http://127.0.0.1:{PORT}", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
