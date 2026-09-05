"""Zero-dependency browser UI for the shopping agent.

Run with ``python -m shopping_agent.ui`` and open http://127.0.0.1:8000.
The page is intentionally served with Python's standard library so the UI does
not introduce another web framework or hide the graph behind a second backend.
"""

from __future__ import annotations

import json
import os
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from shopping_agent.agent import (
    ShoppingState,
    ShoppingServices,
    build_shopping_graph,
    initial_state,
)

from .display import state_to_view

logger = logging.getLogger(__name__)


EXIT_COMMANDS = {"exit", "quit"}
WELCOME_MESSAGE = (
    "Hi! I’m Muse, your shopping assistant. What are you looking to buy?\n"
    "Tell me the product first and I’ll suggest the required and optional "
    "details. Type 'quit' or 'exit' anytime to leave."
)


@dataclass
class ShoppingSession:
    """Conversation state and display history for one browser session."""

    state: ShoppingState = field(default_factory=initial_state)
    messages: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"role": "assistant", "content": WELCOME_MESSAGE}
        ]
    )


class ShoppingApplication:
    """In-memory session manager around the existing shopping graph."""

    def __init__(self) -> None:
        self.services = ShoppingServices.from_environment()
        self.graph = build_shopping_graph(self.services)
        self.sessions: dict[str, ShoppingSession] = {}
        self.lock = threading.Lock()
        self.community_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shopping-community")

    def get_session(self, session_id: str | None) -> tuple[str, ShoppingSession]:
        """Return an existing session or create a new one."""

        with self.lock:
            if session_id and session_id in self.sessions:
                return session_id, self.sessions[session_id]

            new_id = uuid.uuid4().hex
            session = ShoppingSession()
            self.sessions[new_id] = session
            return new_id, session

    def reset(self, session_id: str | None) -> tuple[str, ShoppingSession]:
        """Start a clean conversation while preserving the browser session."""

        with self.lock:
            new_id = session_id or uuid.uuid4().hex
            session = ShoppingSession()
            self.sessions[new_id] = session
            return new_id, session

    def send(self, session: ShoppingSession, message: str) -> dict[str, Any]:
        """Process one browser message and return a frontend view model."""

        message = message.strip()

        if not message:
            return self.view(session)

        session.messages.append({"role": "user", "content": message})

        if message.lower() in EXIT_COMMANDS:
            session.state.update(
                {
                    "finished": True,
                    "assistant_message": "Goodbye! Thanks for shopping with me.",
                    "awaiting_user_input": False,
                }
            )
        elif session.state["finished"]:
            session.state["assistant_message"] = (
                "This shopping session is finished. Click New chat to start again."
            )
        else:
            session.state.update(
                {
                    "last_user_message": message,
                    "input_status": "uninterpreted",
                    "awaiting_user_input": False,
                    "assistant_message": None,
                    "last_error": None,
                }
            )

            try:
                started = monotonic()
                session.state = self.graph.invoke(
                    session.state,
                    {"recursion_limit": 20},
                )
                logger.info("shopping_timing operation=graph_invoke elapsed_ms=%.1f", (monotonic() - started) * 1000)
                self._fetch_community_in_background(session)
            except Exception as error:
                session.state["assistant_message"] = (
                    "I could not complete that step. Please try again."
                )
                session.state["awaiting_user_input"] = True
                session.state["last_error"] = str(error)

        assistant_message = session.state.get("assistant_message")
        if assistant_message:
            session.messages.append(
                {"role": "assistant", "content": assistant_message}
            )

        return self.view(session)

    def _fetch_community_in_background(self, session: ShoppingSession) -> None:
        """Enrich recommendations asynchronously so forum search never delays them."""
        if self.services.community is None or session.state["community_status"] != "not_needed":
            return
        products = list(session.state["qualified_products"])
        if not products:
            return
        product_ids = {product.id for product in products}
        session.state["community_status"] = "pending"
        started = monotonic()

        def collect() -> None:
            try:
                feedback, status, error = self.services.community.fetch(products), "completed", None
            except Exception as exc:  # Community evidence is optional.
                feedback, status, error = {}, "failed", str(exc)
            with self.lock:
                if {product.id for product in session.state["qualified_products"]} == product_ids:
                    session.state.update(community_feedback=feedback, community_status=status)
                    if error:
                        session.state["review_error"] = error
            logger.info("shopping_timing operation=forum_background elapsed_ms=%.1f", (monotonic() - started) * 1000)

        self.community_executor.submit(collect)

    def view(self, session: ShoppingSession) -> dict[str, Any]:
        """Return the state fields needed by the browser."""

        result = state_to_view(session.state)
        result.update(
            {
                "messages": session.messages,
                "groq_configured": bool(os.getenv("GROQ_API_KEY")),
                "searchapi_configured": bool(os.getenv("SEARCHAPI_API_KEY")),
                "model": os.getenv(
                    "GROQ_MODEL",
                    "not configured",
                ),
            }
        )
        return result


class ShoppingRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter for the browser application."""

    server: "ShoppingHTTPServer"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            session_id = self._cookie_session_id()
            new_id, _ = self.server.application.get_session(session_id)
            self._send_text(
                HTML_PAGE,
                content_type="text/html; charset=utf-8",
                session_id=new_id if new_id != session_id else None,
            )
            return

        if self.path == "/api/state":
            session_id = self._cookie_session_id()
            new_id, session = self.server.application.get_session(session_id)
            self._send_json(
                self.server.application.view(session),
                session_id=new_id if new_id != session_id else None,
            )
            return

        self._send_json(
            {"error": "Not found"},
            status=HTTPStatus.NOT_FOUND,
        )

    def do_POST(self) -> None:
        length_text = self.headers.get("Content-Length", "0")

        try:
            content_length = int(length_text)
        except ValueError:
            content_length = 0

        if content_length > 1_000_000:
            self._send_json(
                {"error": "Request is too large."},
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        try:
            payload = json.loads(self.rfile.read(content_length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(
                {"error": "Request body must be valid JSON."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        session_id = self._cookie_session_id()

        if self.path == "/api/chat":
            message = payload.get("message")
            if not isinstance(message, str):
                self._send_json(
                    {"error": "message must be a string."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            new_id, session = self.server.application.get_session(session_id)
            result = self.server.application.send(session, message)
            self._send_json(
                result,
                session_id=new_id if new_id != session_id else None,
            )
            return

        if self.path == "/api/reset":
            new_id, session = self.server.application.reset(session_id)
            self._send_json(
                self.server.application.view(session),
                session_id=new_id if new_id != session_id else None,
            )
            return

        self._send_json(
            {"error": "Not found"},
            status=HTTPStatus.NOT_FOUND,
        )

    def _cookie_session_id(self) -> str | None:
        cookie_header = self.headers.get("Cookie", "")

        for part in cookie_header.split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and name == "shopping_session":
                return value

        return None

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
        session_id: str | None = None,
    ) -> None:
        self._send_text(
            json.dumps(payload, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=status,
            session_id=session_id,
        )

    def _send_text(
        self,
        content: str,
        *,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        session_id: str | None = None,
    ) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if session_id:
            self.send_header(
                "Set-Cookie",
                f"shopping_session={session_id}; Path=/; SameSite=Lax",
            )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep request logs compact while the server is used locally."""

        print(f"[shopping-ui] {format % args}")


class ShoppingHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying the application reference."""

    application: ShoppingApplication


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the local shopping UI server."""

    application = ShoppingApplication()
    server = ShoppingHTTPServer((host, port), ShoppingRequestHandler)
    server.application = application

    print(f"Shopping UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShopping UI stopped.")
    finally:
        server.server_close()


HTML_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Muse — AI shopping assistant</title>
  <style>
    :root {
      --ink: #242236;
      --muted: #77748c;
      --line: #ebe9f2;
      --purple: #6f52d9;
      --purple-dark: #5138b8;
      --lavender: #f1efff;
      --orange: #ff9b62;
      --green: #2ca879;
      --surface: #ffffff;
      --background: #f7f7fb;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }
    body { margin: 0; color: var(--ink); background: var(--background); }
    button, input { font: inherit; }
    button { cursor: pointer; }

    .app-shell { min-height: 100vh; display: grid; grid-template-columns: 250px minmax(0, 1fr); }
    .sidebar { background: #29263c; color: #fff; padding: 28px 20px; display: flex; flex-direction: column; }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; letter-spacing: .08em; font-size: 14px; }
    .brand-mark { width: 34px; height: 34px; border-radius: 12px; display: grid; place-items: center; background: linear-gradient(135deg, #a78cff, #ff9b62); font-weight: 900; }
    .side-copy { color: #b8b4cf; font-size: 13px; line-height: 1.6; margin: 26px 4px 22px; }
    .flow { display: grid; gap: 12px; }
    .flow-step { display: grid; grid-template-columns: 28px 1fr; gap: 10px; align-items: start; color: #d8d5e8; font-size: 13px; }
    .flow-step span { display: grid; place-items: center; width: 25px; height: 25px; border: 1px solid #6f6a85; border-radius: 50%; color: #aaa5c1; font-size: 12px; }
    .flow-step strong { display: block; color: #fff; font-size: 13px; margin-bottom: 3px; }
    .status-box { margin-top: auto; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.1); border-radius: 15px; padding: 13px; font-size: 12px; color: #c7c3d9; }
    .status-dot { width: 8px; height: 8px; display: inline-block; border-radius: 50%; background: var(--green); margin-right: 7px; }
    .status-dot.demo { background: var(--orange); }

    .main { min-width: 0; display: flex; flex-direction: column; }
    .topbar { height: 70px; padding: 0 42px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line); background: rgba(255,255,255,.75); }
    .topbar-title { font-size: 13px; color: var(--muted); }
    .topbar-actions { display: flex; align-items: center; gap: 10px; }
    .model-pill { border: 1px solid var(--line); background: #fff; color: var(--muted); border-radius: 999px; font-size: 11px; padding: 8px 12px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .new-chat { border: 0; background: var(--lavender); color: var(--purple-dark); border-radius: 10px; padding: 9px 13px; font-size: 12px; font-weight: 700; }
    .content { width: min(1100px, calc(100% - 80px)); margin: 0 auto; padding: 42px 0 36px; flex: 1; }
    .hero { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 27px; }
    .eyebrow { text-transform: uppercase; letter-spacing: .13em; color: var(--purple); font-size: 11px; font-weight: 800; }
    h1 { font-size: clamp(30px, 4vw, 48px); line-height: 1.08; letter-spacing: -.045em; margin: 9px 0 10px; }
    .hero p { margin: 0; color: var(--muted); max-width: 540px; line-height: 1.6; }
    .hero-badge { display: flex; align-items: center; gap: 9px; color: var(--muted); font-size: 12px; white-space: nowrap; }
    .spark { width: 32px; height: 32px; border-radius: 12px; display: grid; place-items: center; background: #fff2e9; color: #ed7d40; }

    .workspace { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 22px; align-items: start; }
    .chat-card, .insight-card, .results-card { background: var(--surface); border: 1px solid var(--line); border-radius: 22px; box-shadow: 0 10px 35px rgba(48, 40, 88, .05); }
    .chat-card { min-height: 585px; display: flex; flex-direction: column; overflow: hidden; }
    .chat-header { padding: 17px 20px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 11px; }
    .avatar { width: 34px; height: 34px; border-radius: 12px; display: grid; place-items: center; background: linear-gradient(135deg, #7e62e7, #a994ff); color: #fff; font-weight: 800; }
    .chat-header strong { display: block; font-size: 13px; }
    .chat-header span { color: var(--muted); font-size: 11px; }
    .chat-header .online { margin-left: auto; color: var(--green); font-size: 11px; }
    .chat-header .online::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--green); margin: 0 5px 1px 0; }
    .messages { flex: 1; padding: 24px 22px 10px; overflow: auto; max-height: 465px; }
    .message { display: flex; margin-bottom: 17px; }
    .message.user { justify-content: flex-end; }
    .bubble { max-width: 82%; border-radius: 17px 17px 17px 5px; background: #f4f3f9; padding: 12px 15px; color: #49465b; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
    .message.user .bubble { border-radius: 17px 17px 5px 17px; background: var(--purple); color: #fff; }
    .composer { margin: 0 17px 17px; border: 1px solid #ddd9ee; border-radius: 16px; padding: 7px; display: flex; align-items: center; gap: 8px; background: #fff; }
    .composer:focus-within { border-color: var(--purple); box-shadow: 0 0 0 3px rgba(111,82,217,.1); }
    .composer input { border: 0; outline: 0; flex: 1; min-width: 0; padding: 10px 9px; color: var(--ink); font-size: 13px; }
    .composer input::placeholder { color: #aaa7b9; }
    .send { border: 0; width: 39px; height: 39px; border-radius: 12px; background: var(--purple); color: white; font-size: 17px; }
    .send:disabled { opacity: .5; cursor: wait; }
    .quick-actions { padding: 0 20px 15px; display: flex; gap: 7px; flex-wrap: wrap; }
    .quick-actions button { border: 1px solid var(--line); border-radius: 999px; color: var(--muted); background: #fff; padding: 7px 10px; font-size: 11px; }
    .quick-actions button:hover { border-color: var(--purple); color: var(--purple); }

    .side-stack { display: grid; gap: 17px; }
    .insight-card { padding: 18px; }
    .card-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
    .card-title h2 { font-size: 13px; margin: 0; }
    .card-title span { color: var(--muted); font-size: 11px; }
    .category-chip { display: inline-flex; background: var(--lavender); color: var(--purple-dark); border-radius: 8px; padding: 7px 10px; font-size: 12px; font-weight: 700; margin-bottom: 14px; }
    .attribute-group { margin-top: 14px; }
    .attribute-label { color: var(--muted); text-transform: uppercase; letter-spacing: .08em; font-size: 10px; font-weight: 800; margin-bottom: 8px; }
    .attribute-list { display: flex; flex-wrap: wrap; gap: 7px; }
    .attribute { border: 1px solid var(--line); border-radius: 9px; padding: 7px 9px; font-size: 11px; color: #5b586b; background: #fff; }
    .attribute.required { border-color: #d8cbff; color: var(--purple-dark); background: #faf9ff; }
    .attribute.provided { border-color: #bcebd9; color: #18835f; background: #f2fcf7; }
    .attribute small { display: block; color: #9a96a9; font-size: 9px; margin-top: 3px; }
    .empty-insight { color: var(--muted); font-size: 12px; line-height: 1.6; }
    .hint { color: var(--muted); font-size: 11px; line-height: 1.55; padding-top: 12px; border-top: 1px solid var(--line); margin-top: 16px; }
    .payload { border-top: 1px solid var(--line); margin-top: 17px; padding-top: 12px; }
    .payload summary { cursor: pointer; color: var(--muted); font-size: 11px; }
    .payload pre { overflow: auto; max-height: 220px; font-size: 10px; line-height: 1.5; color: #625b7d; background: #faf9ff; border-radius: 10px; padding: 10px; }

    .results-card { margin-top: 22px; padding: 20px; display: none; }
    .results-card.visible { display: block; }
    .results-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 16px; }
    .results-header h2 { margin: 0; font-size: 16px; }
    .results-header span { color: var(--muted); font-size: 11px; }
    .product-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; }
    .product-card { border: 1px solid var(--line); border-radius: 16px; overflow: hidden; background: #fff; }
    .product-art { height: 112px; padding: 12px; display: flex; justify-content: space-between; align-items: start; background: linear-gradient(135deg, #e9e4ff, #fff0e7); color: var(--purple-dark); }
    .product-icon { width: 48px; height: 48px; display: grid; place-items: center; border-radius: 15px; background: rgba(255,255,255,.65); font-size: 24px; }
    .platform { border-radius: 999px; padding: 5px 8px; background: rgba(255,255,255,.72); color: #726c86; font-size: 9px; }
    .product-info { padding: 14px; }
    .product-info h3 { font-size: 13px; line-height: 1.35; margin: 0 0 7px; }
    .rating { color: #e28a31; font-size: 11px; }
    .rating span { color: var(--muted); }
    .price-row { display: flex; align-items: center; justify-content: space-between; margin-top: 13px; }
    .price { font-size: 17px; font-weight: 800; }
    .cart-button { border: 0; border-radius: 9px; background: var(--purple); color: #fff; padding: 8px 9px; font-size: 10px; font-weight: 700; }
    .cart-button:hover { background: var(--purple-dark); }
    .product-badges { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
    .product-badge { border-radius: 5px; background: #f6f5fa; color: var(--muted); padding: 4px 6px; font-size: 9px; }
    .error-note { color: #b84c4c; background: #fff2f2; border-radius: 10px; padding: 10px; font-size: 11px; margin-top: 12px; }

    @media (max-width: 900px) {
      .app-shell { grid-template-columns: 1fr; }
      .sidebar { display: none; }
      .content { width: min(100% - 28px, 700px); padding-top: 26px; }
      .topbar { padding: 0 14px; }
      .workspace { grid-template-columns: 1fr; }
      .side-stack { grid-template-columns: 1fr 1fr; }
      .product-grid { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 560px) {
      .hero { display: block; }
      .hero-badge { margin-top: 14px; }
      .side-stack { grid-template-columns: 1fr; }
      .product-grid { grid-template-columns: 1fr; }
      .model-pill { display: none; }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">M</div><span>MUSE SHOP</span></div>
      <p class="side-copy">A calmer way to find products that fit your needs — with a little help from AI.</p>
      <div class="flow">
        <div class="flow-step"><span>1</span><div><strong>Tell me what you need</strong>Start with a product or category.</div></div>
        <div class="flow-step"><span>2</span><div><strong>Add the important details</strong>Muse separates required and optional attributes.</div></div>
        <div class="flow-step"><span>3</span><div><strong>Compare your picks</strong>Review matches and add one to cart.</div></div>
      </div>
      <div class="status-box"><span id="status-dot" class="status-dot"></span><span id="status-text">Connecting…</span><div style="margin-top:7px">Type <b>quit</b> or <b>exit</b> anytime to leave.</div></div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="topbar-title">AI-powered product discovery</div>
        <div class="topbar-actions"><div id="model-pill" class="model-pill">Loading model…</div><button id="new-chat" class="new-chat">＋ New chat</button></div>
      </header>

      <div class="content">
        <section class="hero">
          <div><div class="eyebrow">Personal shopping, simplified</div><h1>Find something<br>you’ll love.</h1><p>Tell Muse what you’re looking for. It will understand the product, ask only for useful details, and surface the best matches.</p></div>
          <div class="hero-badge"><div class="spark">✦</div><span>Thoughtful picks,<br>one conversation away.</span></div>
        </section>

        <div class="workspace">
          <section class="chat-card">
            <div class="chat-header"><div class="avatar">M</div><div><strong>Muse Shopping Assistant</strong><span>Understands your preferences</span></div><div class="online">Ready</div></div>
            <div id="messages" class="messages"></div>
            <div class="quick-actions"><button data-message="I want running shoes">Running shoes</button><button data-message="I want a laptop">Find a laptop</button><button data-message="I want snacks">Shop snacks</button></div>
            <form id="composer" class="composer"><input id="message-input" autocomplete="off" placeholder="e.g. running shoes, EU 39, under $150"><button id="send-button" class="send" type="submit">↑</button></form>
          </section>

          <aside class="side-stack">
            <section class="insight-card"><div class="card-title"><h2>Search guidance</h2><span id="guidance-state">Waiting</span></div><div id="guidance-content" class="empty-insight">Start with the product you want to buy. Muse will recommend the details that matter.</div></section>
            <section class="insight-card"><div class="card-title"><h2>How it works</h2><span>3 steps</span></div><div class="empty-insight">The assistant owns the conversation. The search tool receives one stable payload with a category and normalized attributes.</div><div id="payload-container"></div></section>
          </aside>
        </div>

        <section id="results-card" class="results-card"><div class="results-header"><h2>Your curated matches</h2><span id="result-count"></span></div><div id="product-grid" class="product-grid"></div></section>
      </div>
    </main>
  </div>

  <script>
    const messagesEl = document.getElementById('messages');
    const guidanceEl = document.getElementById('guidance-content');
    const guidanceStateEl = document.getElementById('guidance-state');
    const resultsCardEl = document.getElementById('results-card');
    const productGridEl = document.getElementById('product-grid');
    const resultCountEl = document.getElementById('result-count');
    const inputEl = document.getElementById('message-input');
    const sendButtonEl = document.getElementById('send-button');

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>'"]/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
      }[character]));
    }

    function renderMessages(messages) {
      messagesEl.innerHTML = messages.map(item => `
        <div class="message ${item.role === 'user' ? 'user' : 'assistant'}">
          <div class="bubble">${escapeHtml(item.content)}</div>
        </div>`).join('');
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function attributeHtml(item) {
      const stateClass = item.provided ? 'provided' : (item.required ? 'required' : '');
      const mark = item.provided ? '✓ ' : '';
      return `<div class="attribute ${stateClass}">${mark}${escapeHtml(item.name.replaceAll('_', ' '))}${item.reason ? `<small>${escapeHtml(item.reason)}</small>` : ''}</div>`;
    }

    function renderGuidance(data) {
      const requirements = data.requirements;
      const missing = data.missing_required_information || [];
      if (!requirements && !missing.length) {
        guidanceStateEl.textContent = 'Waiting';
        guidanceEl.innerHTML = 'Start with the product you want to buy. Muse will recommend the details that matter.';
        return;
      }
      guidanceStateEl.textContent = data.awaiting_user_input ? 'Needs input' : 'Ready';
      const facts = requirements ? Object.entries(requirements).filter(([, value]) => value != null && value !== '' && (!Array.isArray(value) || value.length)).map(([name, value]) => `<div class="attribute provided">✓ ${escapeHtml(name.replaceAll('_', ' '))}: ${escapeHtml(Array.isArray(value) ? value.join(', ') : value)}</div>`).join('') : '';
      const needed = missing.length ? `<div class="attribute-group"><div class="attribute-label">Still needed</div><div class="attribute-list">${missing.map(value => `<div class="attribute required">${escapeHtml(value)}</div>`).join('')}</div></div>` : '';
      guidanceEl.innerHTML = `<div class="attribute-group"><div class="attribute-label">Current requirements</div><div class="attribute-list">${facts || '<div class="empty-insight">Waiting for product details.</div>'}</div></div>${needed}`;
    }

    function productIcon(category) {
      const value = String(category || '').toLowerCase();
      if (value.includes('shoe')) return '♧';
      if (value.includes('laptop') || value.includes('computer')) return '▣';
      if (value.includes('food') || value.includes('snack')) return '✿';
      return '✦';
    }

    function renderProducts(data) {
      const products = data.products || [];
      if (!products.length) {
        resultsCardEl.classList.remove('visible');
        return;
      }
      resultsCardEl.classList.add('visible');
      resultCountEl.textContent = `${data.total_results || products.length} match${(data.total_results || products.length) === 1 ? '' : 'es'}`;
      productGridEl.innerHTML = products.map(product => {
        const rating = product.rating == null ? 'No rating' : `★ ${Number(product.rating).toFixed(1)} <span>(${product.review_count || 0})</span>`;
        const badges = Object.entries(product.attributes || {}).filter(([key]) => !['query', 'max_price', 'arrival_by', 'must_have'].includes(key)).slice(0, 3).map(([key, value]) => `<span class="product-badge">${escapeHtml(String(value))}</span>`).join('');
        const delivery = product.shipping_info || (product.arrival_date ? `Arrives ${product.arrival_date}` : 'Delivery unavailable');
        const feedback = data.community_feedback?.[product.id]?.available ? 'Community feedback found' : 'No community feedback';
        const image = product.image_url ? `<img src="${escapeHtml(product.image_url)}" alt="" style="max-width:100%;max-height:100%;object-fit:contain">` : `<div class="product-icon">✦</div>`;
        const reasons = (product.reasons || []).slice(0, 2).map(reason => `<span class="product-badge">${escapeHtml(reason)}</span>`).join('');
        const score = product.score == null ? '' : `<span class="product-badge">Score ${Number(product.score).toFixed(1)}</span>`;
        return `<article class="product-card"><div class="product-art">${image}<div class="platform">${escapeHtml(product.seller || product.platform)}</div></div><div class="product-info"><h3>${escapeHtml(product.title)}</h3><div class="rating">${rating}</div><div class="product-badges">${badges}${score}${reasons}<span class="product-badge">${escapeHtml(delivery)}</span><span class="product-badge">${feedback}</span></div><div class="price-row"><div class="price">${escapeHtml(product.currency)} ${Number(product.price).toFixed(2)}</div><a class="cart-button" href="${escapeHtml(product.url)}" target="_blank" rel="noopener">Open product</a></div></div></article>`;
      }).join('');
      productGridEl.querySelectorAll('[data-buy]').forEach(button => button.addEventListener('click', () => sendMessage(`buy ${button.dataset.buy}`)));
    }

    function render(data) {
      renderMessages(data.messages || []);
      renderGuidance(data);
      renderProducts(data);
      const dot = document.getElementById('status-dot');
      const status = document.getElementById('status-text');
      dot.classList.toggle('demo', !data.groq_configured);
      status.textContent = `${data.groq_configured ? `Groq connected · ${data.model}` : 'Groq key missing'} · ${data.searchapi_configured ? 'SearchAPI connected' : 'SearchAPI key missing'}`;
      document.getElementById('model-pill').textContent = data.groq_configured ? data.model : 'Local demo semantics';
      if (data.last_error) {
        guidanceEl.insertAdjacentHTML('beforeend', `<div class="error-note">The last operation needs attention. You can retry the message.</div>`);
      }
    }

    async function request(path, options = {}) {
      const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Request failed');
      return data;
    }

    async function sendMessage(message) {
      const value = String(message || '').trim();
      if (!value || sendButtonEl.disabled) return;
      sendButtonEl.disabled = true;
      sendButtonEl.textContent = '…';
      inputEl.value = '';
      try {
        render(await request('/api/chat', {method: 'POST', body: JSON.stringify({message: value})}));
      } catch (error) {
        guidanceEl.innerHTML = `<div class="error-note">${escapeHtml(error.message)}</div>`;
      } finally {
        sendButtonEl.disabled = false;
        sendButtonEl.textContent = '↑';
        inputEl.focus();
      }
    }

    document.getElementById('composer').addEventListener('submit', event => { event.preventDefault(); sendMessage(inputEl.value); });
    document.querySelectorAll('[data-message]').forEach(button => button.addEventListener('click', () => sendMessage(button.dataset.message)));
    document.getElementById('new-chat').addEventListener('click', async () => { render(await request('/api/reset', {method: 'POST', body: '{}'})); inputEl.focus(); });
    request('/api/state').then(render).catch(error => { guidanceEl.innerHTML = `<div class="error-note">${escapeHtml(error.message)}</div>`; });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    run()
