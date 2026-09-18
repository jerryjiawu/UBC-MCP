# UBC MCP

A suite of MCP (Model Context Protocol) tools for platforms used by UBC professors and students, such as Canvas and CWL.

> **Disclaimer:** This is an unofficial, community-built project and is not affiliated with, endorsed by, or supported by the University of British Columbia (UBC). Use at your own risk and in accordance with UBC's terms of service.

## Status

Early development. Currently implemented:

- `src/cwl.py` — automates CWL (Campus-Wide Login) authentication via Selenium, with a persistent Chrome profile so Duo push isn't required on every run.
- `mcp_server.py` — MCP server exposing browser automation, page reading, file access, and (opt-in) script execution as tools for agents.
- `canvas.py` — placeholder for upcoming Canvas integration.

## Requirements

- Python 3.9+
- Google Chrome (for Selenium's Chrome WebDriver)

## Setup

1. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project root with your CWL credentials:

   ```
   CWL_USERNAME=your_username
   CWL_PASSWORD=your_password
   ```

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

## Project Structure

```
canvas.py        # Canvas MCP tools (in progress)
mcp_server.py    # MCP server: browser automation, file access, script execution
links.json       # saved platform shortcuts (gitignored, created by save_link)
requirements.txt # Python dependencies
src/
  cwl.py         # CWL login automation
```

## Roadmap

- [ ] Canvas API integration (`canvas.py`)
- [ ] Additional UBC platform integrations
