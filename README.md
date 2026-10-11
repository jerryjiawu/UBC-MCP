# UBC MCP

A suite of MCP (Model Context Protocol) tools for platforms used by UBC professors and students, such as Canvas and CWL.

> **Disclaimer:** This is an unofficial, community-built project and is not affiliated with, endorsed by, or supported by the University of British Columbia (UBC). Use at your own risk and in accordance with UBC's terms of service.

## Status

Early development. Currently implemented:

- `src/cwl.py` — automates CWL (Campus-Wide Login) authentication via Selenium, with a persistent Chrome profile so Duo push isn't required on every run. Runs headless by default (set `SELENIUM_HEADLESS=0` in `.env` to always watch it run in a visible window). Posts a Discord webhook notification the moment a Duo push is sent, and if Duo needs a manual step (e.g. "remember this device", picking a verification method), it automatically un-hides the browser at that exact point so you can finish it yourself.
- `mcp_server.py` — MCP server exposing browser automation, page reading, file access, and (opt-in) script execution as tools for agents.
- `google_tasks_mcp.py` — separate MCP server exposing Google Tasks (list/create/complete/delete tasks) to agents.
- `gmail_mcp.py` — separate MCP server exposing read-only Gmail access, restricted to a fixed sender allowlist (`ALLOWED_SENDERS` in the file).
- `rag_server.py` — local RAG server: indexes `src/context/*.txt`/`*.md` with local sentence-transformer embeddings and serves semantic retrieval over HTTP, so the Discord bot only sends the most relevant chunks to Gemini instead of the whole brief.
- `mcp_manager.py` — "MCP Mommy", a local web dashboard + tray icon to start/stop/monitor the MCP servers, the RAG server, and the Discord bot.
- `discord_bot.py` — a Discord bot ("Willow") that answers questions about your UBC status using local RAG retrieval over `src/context/` (falls back to the whole brief if the RAG server is down) via the Gemini API, replying with formatted embeds.
- `canvas.py` — placeholder for upcoming Canvas integration.

## Requirements

- Python 3.9+
- Google Chrome (for Selenium's Chrome WebDriver)

## Setup

1. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project root with your credentials:

   ```
   CWL_USERNAME=your_username
   CWL_PASSWORD=your_password
   GOOGLE_CLIENT_ID=your_google_oauth_client_id
   GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
   ```

   The Google credentials come from an OAuth "Desktop app" client in [Google Cloud Console](https://console.cloud.google.com/apis/credentials) with the Tasks API enabled.

## Usage

Run the CWL login script directly to test authentication:

```powershell
python src/cwl.py
```

### MCP Server

`mcp_server.py` runs an MCP server (stdio transport) that gives an agent tools to:

- `open_url` / `authenticate` — navigate a shared browser session, logging in via CWL automatically when needed.
- `restart_browser` — force-quit and recreate the shared browser session; use if browser tools start erroring (the driver also self-heals automatically on the next call if it detects a dead session, e.g. after a Chrome crash).
- `open_platform` / `save_link` — open a known UBC platform (`webwork`, `canvas`, `brightspace`, `stemble`) or a saved shortcut by name; `save_link(name, url)` records new ones in `links.json`.
- `list_tabs` / `open_tab` / `switch_tab` / `close_tab` — manage multiple browser tabs.
- `get_page_content` / `get_links` / `wait_for` / `screenshot` — read text/links, wait for an element to load, or capture a screenshot.
- `click_element` / `type_text` — interact with the current page.
- `execute_script` — run JavaScript on the page (e.g. to pierce shadow DOM or read structured data).
- `fetch_api` — call a site's API endpoints using the page's authenticated session (cookies), e.g. `GET /api/v1/courses/...`.
- `list_dir` / `read_file` — browse and read files on disk, resolved against the project root regardless of the MCP client's launch directory.
- `run_python` / `run_shell` — execute arbitrary code/commands.

Add it to your MCP client config (e.g. VS Code, Claude Desktop) pointing at:

```powershell
python mcp_server.py
```

**Security notes:**

- `run_python` and `run_shell` give full code-execution privileges and are **disabled by default**. Set `MCP_ALLOW_EXEC=1` in the environment to enable them, and only do so if you trust the connecting agent/client.
- On the known assignment platforms (`webwork`, `canvas`, `brightspace`, `stemble`), the server tries to only allow *viewing* status/content, not editing or submitting work:
  - `click_element` only allows clicking `<a href=...>` navigation links (e.g. quicklinks, LTI launches) there — clicking buttons/submit inputs is blocked.
  - `type_text` is blocked entirely there.
  - `fetch_api` only allows `GET`/`HEAD` there.
  - `execute_script` uses a best-effort heuristic to block scripts that look like they submit/mutate data (POST/PUT/PATCH/DELETE fetches, `form.submit()`) there — **this is not a hard guarantee**, since arbitrary JS can do many things. Treat `execute_script` (and `MCP_ALLOW_EXEC`, which bypasses all of the above via raw HTTP) as elevated-privilege tools.
- `read_file` / `list_dir` can expose secrets (e.g. `.env`) to any connected agent — be mindful of what you point them at.
- Only run this server locally over stdio. Do not expose it over a network.

### Google Tasks MCP Server

`google_tasks_mcp.py` is a separate MCP server (stdio transport) exposing Google Tasks: `list_task_lists`, `list_tasks`, `create_task`, `complete_task`, `delete_task`.

First-time setup requires an interactive browser sign-in, which can't happen inside a normal MCP tool call, so run this once:

```powershell
python google_tasks_mcp.py --auth
```

This opens a browser for Google's OAuth consent screen and saves a refresh token to `google_token.json` (gitignored). After that, add the server to your MCP client config and it refreshes the token silently.

### Gmail MCP Server (read-only, sender-restricted)

`gmail_mcp.py` is a separate MCP server (stdio transport) exposing **read-only** Gmail access: `list_allowed_senders`, `list_emails`, `read_email`.

It's restricted in two independent ways:

1. **OAuth scope** is `gmail.readonly` — there's no send/modify/delete permission at the Google API level at all, regardless of what the code does.
2. **Sender allowlist** — `ALLOWED_SENDERS` in `gmail_mcp.py` (currently `rover.ubc@gmail.com`, `notifications@instructure.com`, `financial.support@askme.ubc.ca`) is baked into every query, and `read_email` re-checks the sender on the fetched message before returning its body. The agent can never see your general inbox, only mail from these specific addresses. Edit `ALLOWED_SENDERS` directly in the file to change the list.

Setup (uses the same Google Cloud OAuth client as Google Tasks — enable the **Gmail API** for it too):

```powershell
python gmail_mcp.py --auth
```

This saves a separate refresh token to `gmail_token.json` (gitignored, scoped only to `gmail.readonly`).

### MCP Mommy (web dashboard + tray icon)

`mcp_manager.py` ("MCP Mommy") runs a local Flask dashboard with a system tray icon to start/stop/restart `mcp_server.py`, `google_tasks_mcp.py`, `gmail_mcp.py`, `rag_server.py`, and `discord_bot.py`, and tail their logs:

```powershell
python mcp_manager.py
```

Then open http://127.0.0.1:5055. It binds to `127.0.0.1` only and has **no authentication** — do not expose it on a network interface or add port forwarding, since anyone who can reach it could start/stop/restart these processes.

The responsive dashboard keeps services in a single row-by-row list, with running/stopped totals, individual service controls, PID and uptime, and expandable recent logs (the latest 50 lines). Status refreshes every 2 seconds without closing logs or replacing focused controls. The daily UBC brief refreshes every 30 seconds, with its reference section expandable. Connection and action failures are displayed on the page; controls are disabled while disconnected or while an action is pending. Its copper-and-charcoal layout is in `templates/mcp_manager.html`, and the dashboard logo uses the existing `src/assets/profile.ico`.

Note: MCP servers use stdio transport, so a server started from MCP Mommy isn't itself "connected" to an MCP client (Claude Desktop/VS Code still launch their own instance via `command`/`args`). MCP Mommy is a process supervisor/log viewer for local development, not an MCP client.

**Important limitation:** MCP Mommy's `ubc-mcp`/`google-tasks-mcp` processes are a **separate, independent set** from whatever Claude Desktop spawned itself. Its Start/Stop/Restart buttons only affect its own copies — they do **not** restart or otherwise touch the instance Claude Desktop is actually talking to over its own stdio pipes. If the live Claude-connected `ubc-mcp` gets into a bad state (e.g. a dead browser session), restarting it from the dashboard won't fix it; you need to either rely on `restart_browser`/the self-healing driver (see below) or restart Claude Desktop itself so it respawns its own copy.

### Local RAG Server

`rag_server.py` is a small local retrieval-augmented-generation service for the Discord bot. It indexes every `.txt`/`.md` file under `src/context/` (currently just `ubc-brief.txt`, but it picks up anything else you add there) using a local sentence-transformer embedding model (`all-MiniLM-L6-v2` by default, override with `RAG_MODEL`) — **no embedding API calls, everything runs on this machine**. It exposes:

- `POST /query` `{"question": "...", "top_k": 4}` → the most relevant chunks (with source file + similarity score)
- `GET /health` → indexing status

Run it standalone with:

```powershell
python rag_server.py
```

Then open http://127.0.0.1:5056/health. It binds to `127.0.0.1` only, same security posture as MCP Mommy (no auth, local-only).

**Setup notes:**
- First run downloads the embedding model from Hugging Face (~90 MB, one-time; cached under `~/.cache/huggingface` afterward — fully offline from then on).
- `sentence-transformers`/`torch` are sizeable dependencies (~500 MB install) — this is the trade-off for genuine local semantic search instead of just dumping the whole brief into every prompt.
- Embeddings are cached in `.rag_cache.npz` (gitignored) and only recomputed when a source file's mtime changes, so restarts are fast.
- `discord_bot.py` calls this server's `/query` endpoint per question and falls back to the whole (size-capped) brief if the RAG server is unreachable, so the bot still works even if this one process is down.

### Discord Bot ("Willow")

`discord_bot.py` is a standalone Discord bot with two jobs:

1. **Duo push notifications** — handled by `src/cwl.py` directly via a Discord webhook (`DISCORD_DUO_WEBHOOK_URL`), independent of whether the bot process is running. The moment a CWL login redirects to Duo, a message is posted so you know to check your phone.
2. **Chat about your UBC status** — DM the bot or @mention it in a server, and it retrieves the most relevant chunks from the local RAG server (see above) for your specific question and answers via the Gemini API, replying with a soft-pink embed and a warm, calming tone.

Setup:

1. Create a Discord bot at the [Discord Developer Portal](https://discord.com/developers/applications), enable the **Message Content** intent, invite it to your server (or just DM it), and add its token to `.env` as `DISCORD_BOT_TOKEN`.
2. Create a webhook on a channel you want Duo notifications posted to (channel settings → Integrations → Webhooks) and add the URL to `.env` as `DISCORD_DUO_WEBHOOK_URL`.
3. Add your [Gemini API key](https://aistudio.google.com/apikey) to `.env` as `GEMINI_API_KEY`.
4. Run it:

   ```powershell
   python discord_bot.py
   ```

**Cost control:** uses Gemini Flash by default (cheapest/fastest tier, has a free tier too, override with `DISCORD_BOT_MODEL`), only responds to DMs/@mentions (not every message in a channel), keeps no conversation history (single-turn per message), and sends only the top few RAG-retrieved chunks per question instead of a growing/whole-brief context. Check [Google AI Studio's usage/billing page](https://aistudio.google.com/) to confirm actual spend for your usage pattern.

## Project Structure

```
canvas.py           # Canvas MCP tools (in progress)
mcp_server.py       # MCP server: browser automation, file access, script execution
google_tasks_mcp.py # MCP server: Google Tasks
gmail_mcp.py        # MCP server: read-only Gmail, restricted to ALLOWED_SENDERS
rag_server.py       # Local RAG server: retrieval over src/context/ for discord_bot.py
mcp_manager.py      # "MCP Mommy": dashboard + tray icon to start/stop/monitor everything below
discord_bot.py      # Discord bot: Duo notifications (via cwl.py) + RAG-backed UBC status Q&A
links.json          # saved platform shortcuts (gitignored, created by save_link)
google_token.json   # Google Tasks OAuth refresh token (gitignored, created by --auth)
gmail_token.json    # Gmail OAuth refresh token (gitignored, created by --auth)
.rag_cache.npz      # cached chunk embeddings (gitignored, rebuilt when context files change)
requirements.txt    # Python dependencies
src/
  cwl.py            # CWL login automation
  context/
    ubc-brief.txt   # status brief indexed by rag_server.py
```

## Roadmap

- [ ] Canvas API integration (`canvas.py`)
- [ ] Additional UBC platform integrations
