# UBC MCP

A suite of MCP (Model Context Protocol) tools for platforms used by UBC professors and students, such as Canvas and CWL.

> **Disclaimer:** This is an unofficial, community-built project and is not affiliated with, endorsed by, or supported by the University of British Columbia (UBC). Use at your own risk and in accordance with UBC's terms of service.

## Status

Early development. Currently implemented:

- `src/cwl.py` — automates CWL (Campus-Wide Login) authentication via Selenium, with a persistent Chrome profile so Duo push isn't required on every run.
- `mcp_server.py` — MCP server exposing browser automation, page reading, file access, and (opt-in) script execution as tools for agents.
- `google_tasks_mcp.py` — separate MCP server exposing Google Tasks (list/create/complete/delete tasks) to agents.
- `mcp_manager.py` — local web dashboard to start/stop/monitor both MCP servers.
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

### MCP Manager (web dashboard)

`mcp_manager.py` runs a local Flask dashboard to start/stop/restart `mcp_server.py` and `google_tasks_mcp.py` and tail their logs:

```powershell
python mcp_manager.py
```

Then open http://127.0.0.1:5055. It binds to `127.0.0.1` only and has **no authentication** — do not expose it on a network interface or add port forwarding, since anyone who can reach it could start/stop/restart these processes.

Note: MCP servers use stdio transport, so a server started from the manager isn't itself "connected" to an MCP client (Claude Desktop/VS Code still launch their own instance via `command`/`args`). The manager is a process supervisor/log viewer for local development, not an MCP client.

## Project Structure

```
canvas.py           # Canvas MCP tools (in progress)
mcp_server.py       # MCP server: browser automation, file access, script execution
google_tasks_mcp.py # MCP server: Google Tasks
mcp_manager.py      # Web dashboard to start/stop/monitor the MCP servers
links.json          # saved platform shortcuts (gitignored, created by save_link)
google_token.json   # Google OAuth refresh token (gitignored, created by --auth)
requirements.txt    # Python dependencies
src/
  cwl.py            # CWL login automation
```

## Roadmap

- [ ] Canvas API integration (`canvas.py`)
- [ ] Additional UBC platform integrations
