# UBC MCP

A suite of MCP (Model Context Protocol) tools for platforms used by UBC professors and students, such as Canvas and CWL.

> **Disclaimer:** This is an unofficial, community-built project and is not affiliated with, endorsed by, or supported by the University of British Columbia (UBC). Use at your own risk and in accordance with UBC's terms of service.

## Status

Early development. Currently implemented:

- `src/cwl.py` — automates CWL (Campus-Wide Login) authentication via Selenium, with a persistent Chrome profile so Duo push isn't required on every run. Runs hidden (headless) by default (set `SELENIUM_HEADLESS=0` in `.env` to start visible instead). Posts a Discord webhook notification the moment a Duo push is sent, and if Duo needs a manual step (e.g. "remember this device", picking a verification method), it automatically shows the browser at that exact point so you can finish it yourself, then hides it again once Duo is done. The AI can also show/hide the browser itself with the `set_browser_visible` MCP tool when it decides you need to step in (a CAPTCHA, a page it can't automate, or you ask to see it). Switching restarts Chrome but keeps open tabs and logins (including session cookies); unsaved form input is lost.
- `mcp_server.py` — MCP server exposing browser automation, page reading, file access, and (opt-in) script execution as tools for agents.
- `google_tasks_mcp.py` — separate MCP server exposing Google Tasks (list/create/complete/delete tasks) to agents.
- `gmail_mcp.py` — separate MCP server exposing read-only Gmail access, restricted to a fixed sender allowlist (`ALLOWED_SENDERS` in the file).
- `rag_server.py` — local RAG server: indexes `src/context/*.txt`/`*.md` with local sentence-transformer embeddings and serves semantic retrieval over HTTP, so the Discord bot only sends the most relevant chunks to Gemini instead of the whole brief.
- `mcp_manager.py` — "MCP Mommy", a local web dashboard + tray icon to start/stop/monitor the MCP servers, the RAG server, and the Discord bot.
- `discord_bot.py` — a Discord bot ("Willow") that answers questions about your UBC status using local RAG retrieval over `src/context/` (falls back to the whole brief if the RAG server is down) via the Gemini API, replying with formatted embeds.
- `prairie_practice/` + `prairie_practice_mcp.py` — **PrairiePractice**: a lightweight local recreation of the PrairieLearn/PrairieTest exam front end (no Docker), plus an MCP server that lets an agent generate practice exams with procedurally generated tests, share them as files, and read a per-error attempt tracker.
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
- `download_file` — download a file (e.g. a Canvas syllabus or course document) using the browser's authenticated session, saving it into `mcp-files/`.
- `list_dir` / `read_file` / `read_pdf` — browse and read files on disk (`read_pdf` extracts text from PDFs), resolved against the project root regardless of the MCP client's launch directory.
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
- `download_file` reuses the browser's session cookies to fetch arbitrary URLs and writes into `mcp-files/` (gitignored, since downloaded course materials are personal/copyrighted) — treat it like `fetch_api` as an elevated-privilege tool.
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

### PrairiePractice (PrairieTest-style practice exams)

A local web app with the same front end you use during a UBC PrairieTest exam. PrairieTest itself is closed source, but during the exam you work in PrairieLearn's exam pages, and PrairieLearn is open source. The app uses PrairieLearn's own stylesheets (`colors.css`, `local.css`, `pageLayout.css`, the element CSS) and its `pl-file-editor` script, copied unmodified into `prairie_practice/static/pl/` (AGPL-3.0; the license is next to them). The templates reproduce the markup of PrairieLearn's student pages: Assessments, the exam overview (status badges, available/awarded points, *Grade N saved answers*, the *All done?* finish dialog), and the question page (file editor with settings and *Restore original file*, *Save & Grade* / *Save only*, submission panels with the file preview and autograder test results, the exam sidebar with its countdown). Grading runs locally; nothing from PrairieLearn's server is installed. Questions are in **C (APSC 160 style)** or Python.

```powershell
python -m prairie_practice.app      # http://127.0.0.1:5070  (also started by MCP Mommy)
```

**C / APSC 160.** C code is compiled with the clang bundled in the `ziglang` pip package (in `requirements.txt`; about 50 MB, nothing installed system-wide). The very first compile takes about 30 s while zig builds its C library cache; after that each compile takes about 0.3 s. There are two kinds of C question:

- *Function questions* give an exact prototype, e.g. `void min_max(const int data[], int size, int *min, int *max)`. A generated test program calls your function once per test and checks the return value, every pointer out-parameter and every non-`const` array. Your file can keep its own `main` for testing; it gets renamed away. Each test runs twice with different values placed just past the end of every array. If the two runs disagree, or one of those values was overwritten, the grader reports an out-of-bounds or uninitialized-memory access, which plain C wouldn't catch.
- *Program questions* have you write the whole `main`: read input with `scanf`, print with `printf`. Output must match exactly, ignoring trailing whitespace. Each failed test shows the input, the expected output and your output.

The 26 built-in C templates cover io, conditionals, loops, functions, arrays, pointers, strings and 2D arrays. Extra C error categories: compile error, segfault, out-of-bounds/uninitialized memory, uninitialized variable, `=` instead of `==`, printf/scanf format mismatch (e.g. a missing `&`), integer division, output format/precision mismatch, and printing nothing. The compiler-warning categories (uninitialized variable, `=` in a condition, missing `return`, format mismatch) only cost points when the attempt actually fails.

**File I/O.** C programs, C functions that take a file name, and Python functions can all read and write files.

- A question declares generated input files (e.g. `data.txt` built from random `file_data`), output files to grade, and optionally a test where the input file is missing. Each test runs in its own empty folder holding only its input files.
- Every C build is force-included with a small header that routes `fopen`/`fclose`/`fscanf`/`fprintf`/`fgets`/... through logging wrappers. Using a NULL `FILE*` crashes the program, as it does on Linux where PrairieLearn grades; Windows' C runtime would otherwise quietly return an error.
- File names are case-sensitive, like on Linux.
- Extra error types: unhandled `fopen` failure, wrong file name, wrong file mode, output file not written, `while (!feof(...))` loops, and forgetting `fclose` (tracked, but it never fails a test).
- Failing tests show the input files, expected vs. your output files, and the file calls your code made. There are six built-in `file_io` templates (five C, one Python).

**Procedural tests, not token-by-token generation.** A problem is a small spec: a prompt, a reference solution, and a one-line type for each parameter (e.g. `"nums": "list[int(-50..50)](0..15)"`). Every time an exam starts, the tests are generated from a fresh random seed. They include boundary cases taken from the type ranges, and the reference solution computes the expected outputs, so the agent never writes test cases. The built-in templates (31 C, 26 Python) randomize their own parameters, so `generate_practice_set` doesn't need the agent to write any problem text.

**Attempts and penalties.** Every graded attempt is classified into error categories: syntax/indentation error, missing or misnamed function, wrong parameters, NameError/TypeError/IndexError/KeyError/…, infinite recursion, infinite loop, missing `return`, printed instead of returned, wrong return type, off-by-one, failed edge cases, wrong answer, and broken constraints ("must be recursive", "no loops", "no `sorted`"; checked statically, scores 0). A wrong attempt deducts the summed penalties of its categories from the question's value for later attempts (default cap 3 points per attempt). Your best attempt counts, and the question locks at 100% or when you run out of attempts. Errors you repeat get more expensive: by default every 5 occurrences of a category add 0.5 points to its penalty, up to 3. The **Gradebook** page shows exam scores, error frequencies, per-topic error rates and recent submissions, and lets you edit every penalty value.

**Sharing.** Each set is saved as `prairie_practice/sets/<title>-<id>.ubcprac.json`. Anyone running this app can import it from the Assessments page or with `import_practice_set`. Shared files contain reference solutions that run locally to generate tests, so only import files from people you trust.

MCP tools (`python prairie_practice_mcp.py`, already registered for Claude Code in `.mcp.json`):

- `generate_practice_set(title, count, topics, difficulty, target_weak_topics, time_limit_min, max_attempts, language)` — build an exam from templates (`language` defaults to `"c"`; `"python"` also works); `target_weak_topics` weights topic choice by your tracked error rate.
- `create_custom_problem(title, prompt, reference, language, kind, function, params, returns, inputs, stdin, constraints, set_id, ...)` — add a custom question from a compact spec (a C function with typed `params`, a C `program` with an input template, or a Python function); the reference solution is checked against the generated tests.
- `list_problem_templates` / `list_practice_sets` / `export_practice_set` / `import_practice_set`
- `get_error_stats` / `get_attempt_history` — what you get wrong most, by category and topic.
- `set_error_penalty(category, points)` / `configure_adaptive_penalties(every, step, cap, max_per_attempt)`
- `open_practice_app(open_browser, set_id)` — start the app if needed and open it.

**Security notes:** binds to 127.0.0.1 with no authentication. Submitted code (Python, or compiled C) runs as an ordinary program on your machine; timeouts only guard against accidents, not malicious code.

## Project Structure

```
canvas.py           # Canvas MCP tools (in progress)
mcp_server.py       # MCP server: browser automation, file access, script execution
google_tasks_mcp.py # MCP server: Google Tasks
gmail_mcp.py        # MCP server: read-only Gmail, restricted to ALLOWED_SENDERS
rag_server.py       # Local RAG server: retrieval over src/context/ for discord_bot.py
mcp_manager.py      # "MCP Mommy": dashboard + tray icon to start/stop/monitor everything below
discord_bot.py      # Discord bot: Duo notifications (via cwl.py) + RAG-backed UBC status Q&A
prairie_practice_mcp.py # MCP server: generate/share practice exams, read the error tracker
prairie_practice/   # PrairieTest-style practice exam app
  app.py            # Flask web UI (PrairieLearn page markup in templates/)
  static/pl/        # PrairieLearn's own CSS + pl-file-editor.js, unmodified (AGPL-3.0)
  problems.py       # built-in problem templates + spec validation
  dsl.py            # input type language -> procedural test inputs
  grader.py         # runs Python code in a subprocess, classifies errors
  c_grader.py       # compiles + runs C (function harness / whole programs), classifies errors
  c_problems.py     # APSC 160-style C templates
  file_problems.py  # file I/O templates
  fileio.py         # input-file rendering, output-file reading, fopen log analysis
  runner.py         # subprocess side of the grader
  store.py          # SQLite: sets, exam instances, attempts, error log, penalties
  sets/             # shareable .ubcprac.json files
  data/             # practice.db + app.log (gitignored)
links.json          # saved platform shortcuts (gitignored, created by save_link)
mcp-files/          # files downloaded via download_file (gitignored, e.g. a Canvas syllabus)
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
