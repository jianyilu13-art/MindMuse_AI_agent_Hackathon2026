# Deploying Muse (one key, live for everyone)

Run the app on a host with a single `SEARCHAPI_API_KEY` set as an environment
variable. Every visitor then gets **live Google Shopping** results through that
one key — they never sign up or configure anything. The key stays server-side
and is never sent to the browser.

The app already reads `HOST`, `PORT`, and `SEARCHAPI_API_KEY` from the
environment, so no code changes are needed — just set them where you deploy.

| Variable | Purpose | Value on a host |
|---|---|---|
| `SEARCHAPI_API_KEY` | live search for all visitors | your key |
| `HOST` | bind address | `0.0.0.0` (Dockerfile sets this) |
| `PORT` | listen port | injected by the platform, else `8000` |
| `SEARCH_CACHE_TTL` | seconds to reuse a query's results | optional, default `600` |

---

## Option 1 — ngrok tunnel (fastest, great for a live demo)

Runs on your laptop and exposes a temporary public URL. Uses your local `.env`.

```bash
# terminal 1: run the app (reads .env, so it's already live)
python -m shopping_agent.ui

# terminal 2: expose it
ngrok http 8000
```

ngrok prints a public `https://…ngrok-free.app` URL — share that. Anyone who
opens it gets live results through your key. Closing ngrok ends the link.

> Sign up once at https://ngrok.com to get a free authtoken, then
> `ngrok config add-authtoken <token>`.

---

## Option 2 — Render / Railway (a stable URL from your GitHub repo)

1. Push the `integration` branch to GitHub (already done).
2. In **Render** (render.com) or **Railway** (railway.app): *New → Web Service*
   → connect this repo → pick the `integration` branch.
3. It auto-detects the **Dockerfile**. (No Dockerfile support? Use build
   command `pip install -e ".[live]"` and start command `python -m shopping_agent.ui`.)
4. Add an environment variable: `SEARCHAPI_API_KEY = your_key`.
   Leave `HOST`/`PORT` alone — the Dockerfile sets `HOST=0.0.0.0` and the
   platform injects `PORT`.
5. Deploy. You get a public `https://…` URL that's live for everyone.

---

## Option 3 — any VPS / cloud VM

```bash
git clone <repo> && cd MindMuse_AI_agent_Hackathon2026 && git checkout integration
pip install -e ".[live]"
HOST=0.0.0.0 PORT=8000 SEARCHAPI_API_KEY=your_key python -m shopping_agent.ui
```

Open the machine's port 8000 (firewall / security group). Put it behind nginx +
HTTPS for anything beyond a quick demo.

---

## Docker (local test of the deploy image)

```bash
docker build -t muse .
docker run -p 8000:8000 -e SEARCHAPI_API_KEY=your_key muse
# open http://localhost:8000
```

---

## Good to know

- **Shared credits.** Every visitor's search spends *your* SearchAPI credits.
  The built-in query cache (`SEARCH_CACHE_TTL`, default 10 min) means repeated
  or identical searches don't re-hit the API. For a wide public launch, add a
  rate limit / CDN in front.
- **Sessions are in-memory.** Each chat lives in the server process; a restart
  clears them and multiple instances don't share them. Fine for a demo; use a
  shared store (e.g. Redis) to scale out.
- **Demo-grade server.** Python's `ThreadingHTTPServer` handles a hackathon
  crowd comfortably; it is not a high-concurrency production server.
- **No key set?** The app simply serves the offline seeded demo — it never
  crashes for lack of a key.
- **Never commit the key.** Set it as an environment variable on the host; keep
  `.env` (git-ignored) for local runs only. Rotate the key in the SearchAPI
  dashboard if it's ever exposed.
