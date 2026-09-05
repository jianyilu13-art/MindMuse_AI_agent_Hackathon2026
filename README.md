# MindMuse Shopping Agent

A conversational shopping assistant. You tell **Muse** what you want in plain
language; it asks only for the details that matter, searches real marketplaces
(via Google Shopping), and returns three curated picks — **Best Overall**,
**Best Value**, and **Best Upgrade** — each with why it was chosen, how to get
it (pickup / delivery), after-sales terms, and a real checkout link.

It never places an order: the final "buy" step always stays with you.

```
 You:  running shoes
 Muse: What size do you need?            (asks only what it needs)
 You:  EU 42
 Muse: What's your budget in SGD?
 You:  under 150
 Muse: Any preferences?
 You:  cushioned, lightweight
 Muse: Here are my top 3 picks →   🥇 Best Overall  💰 Best Value  ⭐ Best Upgrade
```

---

## Table of contents

1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
4. [Run the web UI](#run-the-web-ui)
5. [Offline vs. Live (SearchAPI key)](#offline-vs-live-searchapi-key)
6. [Run the command-line demo](#run-the-command-line-demo)
7. [Run the tests](#run-the-tests)
8. [Project structure](#project-structure)
9. [How the pieces fit](#how-the-pieces-fit)
10. [Troubleshooting](#troubleshooting)
11. [Safety notes](#safety-notes)

---

## How it works

```
  user message
        │
        ▼
  ┌─────────────────────┐   multi-turn, rule-based
  │  conversation.py     │   requirement gathering
  │  product→size→budget │   (no LLM required)
  │  →preferences        │
  └─────────┬───────────┘
            │ UserRequirements
            ▼
  ┌─────────────────────┐
  │  pipeline.run_shopping                                   │
  │                                                          │
  │   search ──▶ recommend ──▶ pickup · service · cart ──▶ customer response
  │  (Google    (weighted     (your back-half tools)   (🥇/💰/⭐ cards)
  │   Shopping)  ranking +                                    │
  │             3 tiers)                                      │
  └──────────────────────────────────────────────────────────┘
            │
            ▼
     Muse UI renders the cards in the chat
```

Everything runs **offline by default** (a seeded search fixture), so you can
try the whole flow with no API key and no network. Add a SearchAPI key to
switch to real Google Shopping results — no code changes needed.

---

## Prerequisites

- **Python 3.10 or newer** (`python3 --version`)
- `pip`
- (Optional) a **SearchAPI.io** key for live results — see
  [Offline vs. Live](#offline-vs-live-searchapi-key)

The UI and pipeline use only the standard library plus **pydantic**. Live
search additionally needs **requests**.

---

## Setup

```bash
# 1. clone and enter the repo
git clone https://github.com/jianyilu13-art/MindMuse_AI_agent_Hackathon2026.git
cd MindMuse_AI_agent_Hackathon2026

# 2. use the integration branch (the complete, runnable version)
git checkout integration

# 3. create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 4. install the package (editable) + live-search dependency
pip install -e .
pip install requests                 # only needed for live Google Shopping
```

> **No-install alternative:** skip `pip install -e .` and prefix every command
> with `PYTHONPATH=src`, e.g. `PYTHONPATH=src python -m shopping_agent.ui`.

---

## Run the web UI

```bash
python -m shopping_agent.ui
```

Then open **http://127.0.0.1:8000** in your browser and chat with Muse.

- Type a product (e.g. `running shoes`) and answer the follow-up questions.
- You can also say everything at once: `running shoes EU 42 under $150 cushioned`.
- Say `skip` to skip a question, `quit` to end — then just type again to start
  a new chat (or use **＋ New chat**, top-right).

The sidebar badge shows the current data source:

- 🟠 **Offline demo · seeded search** — no key configured (default)
- 🟢 **Live · Google Shopping** — a SearchAPI key is configured

Stop the server with `Ctrl+C`.

---

## Offline vs. Live (SearchAPI key)

By default the app uses a small seeded dataset so it always runs. To get **real
Google Shopping results**, provide a SearchAPI.io key.

### 1. Get a key

1. Go to **https://www.searchapi.io** and sign up (free trial credits).
2. Open the **Dashboard** and copy your **API Key**.

### 2. Configure it

Create a file named `.env` in the project root:

```bash
# .env  (this file is git-ignored — never commit it)
SEARCHAPI_API_KEY=your_key_here
```

That's it — the next run auto-detects the key and switches to live search. A
`.env.example` is included as a template.

Prefer not to use a file? Pass it inline for one run:

```bash
SEARCHAPI_API_KEY=your_key_here python -m shopping_agent.ui
```

### Deploy it live for everyone (one key, no per-user setup)

Host the app with a single `SEARCHAPI_API_KEY` set on the server and **every
visitor gets live results through that one key** — they never sign up or
configure anything. A `Dockerfile` and `Procfile` are included; see
**[DEPLOY.md](DEPLOY.md)** for ngrok / Render / Railway / VPS steps.

> **Security:** `.env` is listed in `.gitignore`, so your key stays local and is
> never committed. If a key is ever exposed, regenerate it in the SearchAPI
> dashboard.

---

## Run the command-line demo

Prefer the terminal? A one-shot end-to-end demo prints the same picks without
the browser:

```bash
python examples/run_pipeline.py
```

It runs a sample request (running shoes, budget S$150, cushioned/lightweight)
through the full pipeline and prints the 🥇/💰/⭐ cards. Edit the
`UserRequirements(...)` block at the top of the file to try other queries.

---

## Run the tests

```bash
python -m pytest -q
```

All tests are deterministic and network-free — they force the offline search
fixture even if a real key is present in `.env`, so the suite is fast and
repeatable.

---

## Project structure

```
src/shopping_agent/
├── schemas/            # the shared data contract (pydantic)
│   ├── product.py          Product (Decimal price, SGD, image, delivery, policy…)
│   ├── user_requirements.py UserRequirements + Weights
│   ├── review.py           Review / ReviewSummary
│   └── results.py          Recommendation, PickupInfo, CartResult, ProductCard…
├── processing/
│   └── scoring.py          normalize + preference matching (pure math)
├── tools/              # the shopping capabilities
│   ├── search.py           front-half: Google Shopping search + normalize
│   ├── recommendation.py   weighted ranking + curated 🥇/💰/⭐ picks
│   ├── pickup.py           can you get it in time? store pickup / delivery ETA
│   ├── customer_service.py return/warranty summary, seller Q, arrival checklist
│   ├── cart.py             checkout handoff link (never places an order)
│   ├── customer_response.py assembles the customer-facing cards
│   └── context.py          in-memory Session shared by the tools
├── ui/                 # the Muse web UI
│   ├── web.py              zero-dependency chat server (stdlib)
│   ├── conversation.py     rule-based multi-turn requirement gathering
│   └── __main__.py         `python -m shopping_agent.ui`
├── pipeline.py         # end-to-end orchestrator (search → … → response)
└── config.py           # loads .env, exposes the SearchAPI key

examples/
├── run_pipeline.py     # one-shot end-to-end demo
└── demo_backhalf.py    # back-half tools only (recommendation/pickup/…)

tests/                  # 61 tests (unit + integration + conversation)
```

---

## How the pieces fit

- **The contract (`schemas/`)** is the single source of truth. Every tool reads
  and writes `Product`, `UserRequirements`, and the result types — so the search
  source, the ranker, and the UI all speak the same language.
- **`search.py`** turns a request into a query, calls Google Shopping (or the
  offline fixture), and normalizes each result into a unified `Product`.
- **`recommendation.py`** applies hard filters (budget, must-haves), scores the
  survivors on price / speed / preference, and produces the three curated tiers.
  *Best Upgrade* may exceed budget and is scored on fit only ("functional
  match"), so its percentage is honest.
- **The back-half tools** (`pickup`, `customer_service`, `cart`) enrich each
  pick, and **`customer_response.py`** assembles the final cards.
- **`pipeline.py`** wires it together; **`conversation.py`** drives it over a
  chat. A real LLM planner or a LangGraph agent can replace either layer later —
  the tools and schemas stay the same.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: shopping_agent` | Run `pip install -e .`, or prefix commands with `PYTHONPATH=src`. |
| Badge stays 🟠 Offline after adding a key | Check `.env` is in the project root and the line reads `SEARCHAPI_API_KEY=...`; restart the server. |
| Live search errors / `requests` missing | `pip install requests`; confirm the key is valid and has credits. |
| Port 8000 already in use | Stop the other process, or change `PORT` at the top of `src/shopping_agent/ui/web.py`. |
| Chat feels "stuck" after `quit` | Just type a new product — it starts a fresh chat (or click **＋ New chat**). |

---

## Safety notes

- **No orders are ever placed.** The app only prepares a checkout link (a real
  Amazon add-to-cart link where possible, otherwise the product page). You
  complete checkout yourself.
- **After-sales terms are never invented** — if a listing doesn't state a return
  or warranty policy, Muse says so instead of guessing.
- **Secrets stay local.** `.env` is git-ignored; keys are read from the
  environment and never written into tracked files.
