"""Muse web UI — conversational, wired to the integrated pipeline.

Multi-turn chat that gathers requirements (product -> size -> budget ->
preferences) and then runs the *real* integration pipeline (search ->
recommend -> pickup/service/cart), rendering the curated 🥇/💰/⭐ cards inside
the conversation. Zero dependencies (Python standard library); offline via the
seeded search fixture, or real Google Shopping with SEARCHAPI_API_KEY.

    python -m shopping_agent.ui            # then open http://127.0.0.1:8000
"""

from __future__ import annotations

import html
import os
import sys
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from shopping_agent.agent import initial_state, run_turn
from shopping_agent.llm.model import get_llm
from shopping_agent.schemas import PickTier

PORT = 8000
_SESSIONS: dict[str, dict] = {}          # sid -> AgentState
_GREETING = "Hi! I'm Muse, your shopping assistant. What are you looking to buy today?"


def _new_session() -> dict:
    """A fresh agent conversation (LLM if a key is configured, else rules)."""
    state = initial_state("ui", llm=get_llm())
    state["history"] = [{"role": "assistant", "content": _GREETING}]
    return state

_TIER = {
    PickTier.BEST_OVERALL: ("Best Overall", "🥇", "overall"),
    PickTier.BEST_VALUE: ("Best Value", "💰", "value"),
    PickTier.BEST_UPGRADE: ("Best Upgrade", "⭐", "upgrade"),
}

CSS = """
  :root{--ink:#242236;--muted:#77748c;--line:#ebe9f2;--purple:#6f52d9;
    --purple-dark:#5138b8;--lavender:#f1efff;--orange:#ff9b62;--green:#2ca879;
    --surface:#fff;--bg:#f7f7fb;
    font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  *{box-sizing:border-box}
  body{margin:0;color:var(--ink);background:var(--bg)}
  .layout{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
  .sidebar{background:#29263c;color:#fff;padding:28px 20px;display:flex;flex-direction:column;gap:26px}
  .brand{display:flex;align-items:center;gap:11px;font-weight:800}
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
  .status-dot.live{background:var(--green)}
  .main{display:flex;flex-direction:column}
  .topbar{height:70px;padding:0 42px;display:flex;align-items:center;justify-content:space-between;
    border-bottom:1px solid var(--line);background:rgba(255,255,255,.75)}
  .topbar-title{font-size:13px;color:var(--muted)}
  .newchat{border:0;background:var(--lavender);color:var(--purple-dark);border-radius:10px;
    padding:9px 14px;font-size:12px;font-weight:700;text-decoration:none}
  .content{padding:30px 42px 60px;max-width:940px;width:100%}
  .eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--purple);font-size:11px;font-weight:800}
  .hero h1{font-size:2rem;line-height:1.1;margin:.35rem 0 .4rem;letter-spacing:-.02em}
  .hero p{margin:0 0 22px;color:var(--muted);max-width:540px;line-height:1.6}
  /* chat */
  .chat-card{background:var(--surface);border:1px solid var(--line);border-radius:22px;
    box-shadow:0 10px 35px rgba(48,40,88,.05);overflow:hidden}
  .chat-header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:11px}
  .avatar{width:34px;height:34px;border-radius:12px;display:grid;place-items:center;
    background:linear-gradient(135deg,#7e62e7,#a994ff);color:#fff;font-weight:800}
  .chat-header b{font-size:14px}.chat-header small{color:var(--muted);font-size:11px;display:block}
  .chat-header .online{margin-left:auto;color:var(--green);font-size:11px}
  .chat-header .online::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;
    background:var(--green);margin:0 5px 1px 0}
  .messages{padding:20px;display:flex;flex-direction:column;gap:12px;max-height:none}
  .message{display:flex}.message.user{justify-content:flex-end}
  .bubble{max-width:78%;border-radius:17px 17px 17px 5px;background:#f4f3f9;padding:11px 15px;
    color:#49465b;font-size:13.5px;line-height:1.6;white-space:pre-wrap}
  .message.user .bubble{border-radius:17px 17px 5px 17px;background:var(--purple);color:#fff}
  .composer{margin:0 17px 17px;border:1px solid #ddd9ee;border-radius:16px;padding:7px;display:flex;
    align-items:center;gap:8px;background:#fff}
  .composer:focus-within{border-color:var(--purple);box-shadow:0 0 0 3px rgba(111,82,217,.1)}
  .composer input{border:0;outline:0;flex:1;min-width:0;padding:10px 9px;color:var(--ink);font-size:13.5px;
    font-family:inherit;background:transparent}
  .send{border:0;width:39px;height:39px;flex:none;border-radius:12px;background:var(--purple);
    color:#fff;font-size:17px;cursor:pointer}
  .send:hover{background:var(--purple-dark)}
  /* results */
  .results-head{margin:28px 0 16px;display:flex;align-items:baseline;gap:10px}
  .results-head h2{font-size:1.2rem;margin:0}.results-head span{color:var(--muted);font-size:12px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(258px,1fr));gap:18px}
  .product-card{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#fff;
    box-shadow:0 10px 35px rgba(48,40,88,.05);display:flex;flex-direction:column}
  .art{height:100px;padding:13px;display:flex;justify-content:space-between;align-items:flex-start;
    background:linear-gradient(135deg,#e9e4ff,#fff0e7)}
  .icon{width:50px;height:50px;display:grid;place-items:center;border-radius:15px;
    background:rgba(255,255,255,.7);font-size:25px}
  .platform{border-radius:999px;padding:5px 9px;background:rgba(255,255,255,.78);color:#726c86;
    font-size:10px;font-weight:700}
  .badge{align-self:flex-start;margin:-14px 0 0 13px;position:relative;z-index:1;font-size:11px;
    font-weight:800;padding:5px 10px;border-radius:999px;color:#fff}
  .badge.overall{background:var(--purple)}.badge.value{background:var(--green)}.badge.upgrade{background:var(--orange)}
  .pbody{padding:14px 15px 16px;display:flex;flex-direction:column;gap:7px;flex:1}
  .ptitle{font-weight:700;font-size:14px;line-height:1.35;margin:0}
  .price-row{display:flex;align-items:baseline;gap:8px}.price{font-size:1.15rem;font-weight:800}
  .rating{color:var(--muted);font-size:12px}
  .match{font-size:11px;font-weight:800;color:var(--purple)}
  .reason{font-size:12.5px;color:#5b586b;line-height:1.5}
  .facts{display:flex;flex-direction:column;gap:4px;margin-top:2px}.fact{font-size:11.5px;color:var(--muted)}
  .cart-button{margin-top:auto;border:0;border-radius:11px;background:var(--purple);color:#fff;
    padding:10px;font-size:12px;font-weight:700;cursor:pointer;text-decoration:none;text-align:center;display:block}
  .cart-button:hover{background:var(--purple-dark)}
  .cart-note{font-size:10.5px;color:var(--muted);margin-top:5px;line-height:1.4}
  .footer{margin-top:24px;color:var(--muted);font-size:12px}
  @media(max-width:820px){.layout{grid-template-columns:1fr}.sidebar{display:none}}
"""


def _card(card) -> str:
    tier = _TIER.get(card.tier)
    badge = ""
    if tier:
        label, emoji, cls = tier
        badge = f"<div class='badge {cls}'>{emoji} {html.escape(label)}</div>"
    rating = f"<span class=rating>{card.rating}★</span>" if card.rating is not None else ""
    match = f"<div class=match>{card.match_pct}% {html.escape(card.match_label)}</div>" if card.match_pct is not None else ""
    facts = []
    if card.availability:
        facts.append(f"<div class=fact>🚚 {html.escape(card.availability)}</div>")
    if card.after_sales:
        facts.append(f"<div class=fact>📋 {html.escape(card.after_sales)}</div>")
    facts_html = f"<div class=facts>{''.join(facts)}</div>" if facts else ""
    cta = ""
    if card.checkout_url:
        cta = (f"<a class=cart-button href=\"{html.escape(card.checkout_url)}\" target=_blank rel=noopener>Checkout &rarr;</a>"
               f"<div class=cart-note>{html.escape(card.checkout_note)}</div>")
    return ("<div class=product-card>"
            f"<div class=art><div class=icon>🛍</div><span class=platform>{html.escape(card.platform)}</span></div>"
            f"{badge}<div class=pbody>"
            f"<p class=ptitle>{html.escape(card.title)}</p>"
            f"<div class=price-row><span class=price>{html.escape(card.price)}</span>{rating}</div>"
            f"{match}<div class=reason>{html.escape(card.reason)}</div>{facts_html}{cta}"
            "</div></div>")


def _results_html(session: dict) -> str:
    resp = session.get("response")
    if not resp or not resp.cards:
        return ""
    cards = "".join(_card(c) for c in resp.cards)
    return (f"<div class=results-head><h2>{html.escape(resp.headline)}</h2>"
            f"<span>{len(resp.cards)} picks · nothing ordered</span></div>"
            f"<div class=grid>{cards}</div>"
            f"<div class=footer>{html.escape(resp.footer)}</div>")


def _messages_html(session: dict) -> str:
    rows = []
    for m in session.get("history", []):
        role = "user" if m["role"] == "user" else "assistant"
        rows.append(f"<div class='message {role}'><div class=bubble>{html.escape(m['content'])}</div></div>")
    return "".join(rows)


def _status_box() -> str:
    from shopping_agent.config import searchapi_key

    if searchapi_key():
        return ("<div class=status-box><span class='status-dot live'></span>"
                "Live · Google Shopping · no order is ever placed</div>")
    return ("<div class=status-box><span class=status-dot></span>"
            "Offline demo · seeded search · no order is ever placed</div>")


def _page(session: dict) -> str:
    placeholder = "Type a product to start again…" if session.get("finished") else "Type your reply…"
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Muse — Shopping Agent</title>"
        "<link rel=preconnect href='https://fonts.googleapis.com'>"
        "<link rel=stylesheet href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap'>"
        f"<style>{CSS}</style></head><body><div class=layout>"
        "<aside class=sidebar>"
        "<div class=brand><span class=brand-mark>M</span> MUSE SHOP</div>"
        "<p class=tagline>A calmer way to find products that fit your needs — powered by the live pipeline.</p>"
        "<ol class=steps>"
        "<li class=step><span class=n>1</span><div><b>Tell Muse what you need</b><span>Just the product to start.</span></div></li>"
        "<li class=step><span class=n>2</span><div><b>Answer a couple of questions</b><span>Size, budget, preferences.</span></div></li>"
        "<li class=step><span class=n>3</span><div><b>Compare &amp; check out</b><span>Real picks, pickup, returns.</span></div></li>"
        "</ol>"
        f"{_status_box()}"
        "</aside>"
        "<main class=main>"
        "<div class=topbar><span class=topbar-title>AI-powered product discovery</span>"
        "<a class=newchat href='/?new=1'>＋ New chat</a></div>"
        "<div class=content>"
        "<div class=hero><div class=eyebrow>Personal shopping, simplified</div>"
        "<h1>Find something you&rsquo;ll love.</h1>"
        "<p>Tell Muse what you&rsquo;re looking for. It asks only for useful details, then surfaces the best matches.</p></div>"
        "<div class=chat-card>"
        "<div class=chat-header><span class=avatar>M</span>"
        "<div><b>Muse Shopping Assistant</b><small>Understands your preferences</small></div>"
        "<span class=online>Ready</span></div>"
        f"<div class=messages>{_messages_html(session)}</div>"
        "<form class=composer method=post action=/>"
        f"<input name=msg autocomplete=off placeholder='{placeholder}' autofocus>"
        "<button class=send type=submit>&uarr;</button>"
        "</form></div>"
        f"{_results_html(session)}"
        "</div></main></div></body></html>"
    )


class Handler(BaseHTTPRequestHandler):
    def _sid(self) -> tuple[str, bool]:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        if "sid" in cookie and cookie["sid"].value in _SESSIONS:
            return cookie["sid"].value, False
        return uuid.uuid4().hex, True

    def _send(self, body: bytes, sid: str, set_cookie: bool, status: int = 200, location: str | None = None):
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        if set_cookie:
            self.send_header("Set-Cookie", f"sid={sid}; Path=/; SameSite=Lax")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_response(404); self.end_headers(); return
        sid, is_new = self._sid()
        if parse_qs(parsed.query).get("new"):
            _SESSIONS[sid] = _new_session()  # reset conversation
        session = _SESSIONS.setdefault(sid, _new_session())
        self._send(_page(session).encode("utf-8"), sid, is_new)

    def do_POST(self):  # noqa: N802
        sid, is_new = self._sid()
        session = _SESSIONS.setdefault(sid, _new_session())
        length = int(self.headers.get("Content-Length", 0) or 0)
        data = parse_qs(self.rfile.read(length).decode("utf-8")) if length else {}
        msg = (data.get("msg", [""])[0] or "").strip()
        if msg:
            if session.get("finished"):  # finished -> any new message restarts
                session = _SESSIONS[sid] = _new_session()
            try:
                _SESSIONS[sid] = run_turn(session, msg)
            except Exception as exc:  # keep the chat alive
                session.setdefault("history", []).append(
                    {"role": "assistant", "content": f"Sorry, something went wrong: {exc}"})
        # Post/Redirect/Get so a refresh doesn't resend the message
        self._send(b"", sid, is_new, status=303, location="/")

    def log_message(self, *args):  # quiet
        pass


def main() -> None:
    # HOST/PORT come from the environment so the same code runs locally
    # (127.0.0.1) and on a host/PaaS (0.0.0.0, platform-assigned $PORT).
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", str(PORT)))
    print(f"Muse UI  ->  http://{host}:{port}", flush=True)
    try:
        ThreadingHTTPServer((host, port), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
