"""MCP server exposing browser automation, script execution, and file access to agents.

SECURITY WARNING: the run_python/run_shell tools give any connected agent full
code-execution privileges on this machine, and read_file/list_dir can expose
secrets (e.g. .env). They are gated behind MCP_ALLOW_EXEC=1 in the environment
so they are off by default. Only run this server locally over stdio, never
expose it over a network, and only connect trusted MCP clients to it. Note
that enabling MCP_ALLOW_EXEC lets an agent bypass the assignment-edit
restriction below via raw HTTP requests, so keep it disabled unless needed.
"""
import os
import json
import re
import subprocess
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from cwl import CWL_login, get_driver  # noqa: E402

load_dotenv()

EXEC_ENABLED = os.getenv("MCP_ALLOW_EXEC") == "1"

# Resolve relative file paths against the project root, not the MCP client's launch cwd
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LINKS_FILE = os.path.join(PROJECT_ROOT, "links.json")


def _resolve_path(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def _load_links() -> dict:
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_links(links: dict) -> None:
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(links, f, indent=2)


# Known UBC platforms, usable by short name with open_platform()
PLATFORMS = {
    "webwork": "https://webwork.elearning.ubc.ca/webwork2",
    "canvas": "https://canvas.ubc.ca",
    "brightspace": "https://ubc.brightspace.com",
    "stemble": "https://app.stemble.com",
}

# These are all assignment platforms: the agent may only view status there, never submit/edit work
_RESTRICTED_HOSTS = {urlparse(url).hostname for url in PLATFORMS.values()}

# Best-effort heuristic for scripts that look like they submit/mutate data (not a hard guarantee)
_MUTATION_PATTERN = re.compile(
    r"""method\s*:\s*['"](post|put|patch|delete)['"] | \.submit\s*\( | requestSubmit\s*\(""",
    re.IGNORECASE | re.VERBOSE,
)

mcp = FastMCP("ubc-mcp")

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = get_driver()
    return _driver


def _current_host(driver) -> str:
    return urlparse(driver.current_url).hostname or ""


def _blocked_on_restricted_platform(driver, action: str) -> str | None:
    host = _current_host(driver)
    if host in _RESTRICTED_HOSTS:
        return (
            f"error: {action} is blocked on {host} — this server only allows viewing "
            "assignment status there, not editing or submitting work"
        )
    return None


@mcp.tool()
def open_url(url: str) -> str:
    """Navigate the shared browser to a URL and return its title and final URL."""
    driver = _get_driver()
    driver.get(url)
    return f"title={driver.title!r} url={driver.current_url!r}"


@mcp.tool()
def authenticate(url: str) -> str:
    """Navigate to a UBC CWL-protected page and log in automatically if a login form is shown."""
    driver = _get_driver()
    CWL_login(driver, url)
    return f"title={driver.title!r} url={driver.current_url!r}"


@mcp.tool()
def open_platform(name: str) -> str:
    """Open a known platform or saved link by short name (webwork, canvas, brightspace, stemble, or anything added via save_link), authenticating via CWL if needed."""
    key = name.lower().strip()
    url = PLATFORMS.get(key) or _load_links().get(key)
    if not url:
        known = sorted(set(PLATFORMS) | set(_load_links()))
        return f"error: unknown platform/link {name!r}. Known: {', '.join(known)}"
    driver = _get_driver()
    CWL_login(driver, url)
    return f"title={driver.title!r} url={driver.current_url!r}"


@mcp.tool()
def save_link(name: str, url: str) -> str:
    """Save a named shortcut URL (e.g. 'webwork-math100') for later use with open_platform."""
    links = _load_links()
    links[name.lower().strip()] = url
    _save_links(links)
    return f"saved {name!r} -> {url!r}"


@mcp.tool()
def list_tabs() -> str:
    """List open browser tabs with their index, title, and URL (current tab marked with *)."""
    driver = _get_driver()
    current = driver.current_window_handle
    lines = []
    for i, handle in enumerate(driver.window_handles):
        driver.switch_to.window(handle)
        marker = "*" if handle == current else " "
        lines.append(f"{marker}[{i}] title={driver.title!r} url={driver.current_url!r}")
    driver.switch_to.window(current)
    return "\n".join(lines)


@mcp.tool()
def open_tab(url: str = "about:blank") -> str:
    """Open a new browser tab (optionally navigating to a URL) and switch to it."""
    driver = _get_driver()
    driver.switch_to.new_window("tab")
    if url and url != "about:blank":
        driver.get(url)
    return f"opened tab [{len(driver.window_handles) - 1}] title={driver.title!r} url={driver.current_url!r}"


@mcp.tool()
def switch_tab(index: int) -> str:
    """Switch the active tab to the one at the given index (see list_tabs)."""
    driver = _get_driver()
    handles = driver.window_handles
    if not (0 <= index < len(handles)):
        return f"error: index {index} out of range (0..{len(handles) - 1})"
    driver.switch_to.window(handles[index])
    return f"switched to tab [{index}] title={driver.title!r} url={driver.current_url!r}"


@mcp.tool()
def close_tab(index: int = -1) -> str:
    """Close a tab by index (default -1: the current tab) and switch to the next available one."""
    driver = _get_driver()
    handles = driver.window_handles
    target_index = index if index >= 0 else handles.index(driver.current_window_handle)
    if not (0 <= target_index < len(handles)):
        return f"error: index {target_index} out of range (0..{len(handles) - 1})"
    driver.switch_to.window(handles[target_index])
    driver.close()
    remaining = driver.window_handles
    if remaining:
        driver.switch_to.window(remaining[0])
        return f"closed tab [{target_index}], now on title={driver.title!r} url={driver.current_url!r}"
    return f"closed tab [{target_index}], no tabs remain"


@mcp.tool()
def get_page_content(max_chars: int = 5000) -> str:
    """Return the visible text of the current page in the shared browser, truncated to max_chars."""
    driver = _get_driver()
    text = driver.find_element(By.TAG_NAME, "body").text
    return text[:max_chars]


@mcp.tool()
def get_links(max_links: int = 200) -> str:
    """List anchor links on the current page as 'text -> href' pairs, useful for finding navigation targets."""
    driver = _get_driver()
    lines = []
    for el in driver.find_elements(By.TAG_NAME, "a")[:max_links]:
        href = el.get_attribute("href") or ""
        text = el.text.strip().replace("\n", " ")
        if href:
            lines.append(f"{text!r} -> {href}")
    return "\n".join(lines)


@mcp.tool()
def wait_for(css_selector: str, timeout: int = 10) -> str:
    """Wait until an element matching a CSS selector is present on the page (use after navigation before reading content)."""
    driver = _get_driver()
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )
    except TimeoutException:
        return f"error: {css_selector!r} did not appear within {timeout}s"
    return f"found {css_selector!r}"


@mcp.tool()
def screenshot(filename: str = "") -> str:
    """Save a screenshot of the current page to the screenshots/ folder and return its path."""
    driver = _get_driver()
    shots_dir = os.path.join(PROJECT_ROOT, "screenshots")
    os.makedirs(shots_dir, exist_ok=True)
    name = filename or f"screenshot-{int(__import__('time').time())}.png"
    if not name.lower().endswith(".png"):
        name += ".png"
    target = os.path.join(shots_dir, name)
    driver.save_screenshot(target)
    return target


@mcp.tool()
def execute_script(code: str) -> str:
    """Run synchronous JavaScript in the current page (e.g. to pierce shadow DOM or read structured data)
    and return its JSON-serializable result. This is an elevated-privilege tool: it can read cookies,
    session tokens, and page internals. On assignment platforms, scripts that look like they submit or
    mutate data (POST/PUT/PATCH/DELETE fetches, form.submit()) are blocked as a best-effort heuristic --
    not a hard guarantee. Prefer fetch_api for calling site APIs, since it enforces GET-only there.
    """
    driver = _get_driver()
    host = _current_host(driver)
    if host in _RESTRICTED_HOSTS and _MUTATION_PATTERN.search(code):
        return (
            f"error: execute_script looks like it submits/mutates data on {host} — "
            "this server only allows viewing assignment status, not editing/submitting work"
        )
    try:
        result = driver.execute_script(f"return (function() {{ {code} }})();")
    except Exception as e:
        return f"error: {e}"
    try:
        return json.dumps(result, default=str)[:20000]
    except TypeError:
        return str(result)[:20000]


@mcp.tool()
def fetch_api(url: str, method: str = "GET", body: str = "") -> str:
    """Call an API endpoint using the current page's authenticated session (cookies) and return the response.

    'url' may be a path (resolved against the current page's origin) or a full URL. On assignment
    platforms only GET/HEAD are allowed -- this tool cannot be used to submit or edit work there.
    """
    driver = _get_driver()
    host = _current_host(driver)
    method = method.upper().strip()
    if host in _RESTRICTED_HOSTS and method not in ("GET", "HEAD"):
        return f"error: {method} is blocked on {host} — only GET/HEAD are allowed on assignment platforms"

    script = """
    var callback = arguments[arguments.length - 1];
    var url = arguments[0], method = arguments[1], body = arguments[2];
    var opts = {method: method, credentials: 'include'};
    if (body) { opts.body = body; opts.headers = {'Content-Type': 'application/json'}; }
    fetch(url, opts)
      .then(function(r) { return r.text().then(function(t) { return {status: r.status, body: t}; }); })
      .then(function(res) { callback(res); })
      .catch(function(err) { callback({error: String(err)}); });
    """
    driver.set_script_timeout(15)
    try:
        result = driver.execute_async_script(script, url, method, body or None)
    except Exception as e:
        return f"error: {e}"
    return json.dumps(result)[:20000]


@mcp.tool()
def click_element(css_selector: str) -> str:
    """Click the first element matching a CSS selector on the current page.

    On assignment platforms, only navigation is allowed (an <a> element with an href, e.g. a
    quicklink or LTI launch) -- clicking anything else (buttons, submit inputs, etc.) is blocked.
    """
    driver = _get_driver()
    host = _current_host(driver)
    try:
        element = driver.find_element(By.CSS_SELECTOR, css_selector)
    except NoSuchElementException as e:
        return f"error: {e}"
    if host in _RESTRICTED_HOSTS:
        is_link = element.tag_name.lower() == "a" and element.get_attribute("href")
        if not is_link:
            return (
                f"error: click_element is blocked on {host} for non-navigation elements — "
                "this server only allows following links there, not submitting/editing work"
            )
    try:
        element.click()
    except TimeoutException as e:
        return f"error: {e}"
    return f"clicked {css_selector!r}, now at {driver.current_url!r}"


@mcp.tool()
def type_text(css_selector: str, text: str, submit: bool = False) -> str:
    """Type text into the first element matching a CSS selector, optionally pressing Enter. Blocked on assignment platforms."""
    from selenium.webdriver.common.keys import Keys

    driver = _get_driver()
    blocked = _blocked_on_restricted_platform(driver, "type_text")
    if blocked:
        return blocked
    try:
        field = driver.find_element(By.CSS_SELECTOR, css_selector)
    except NoSuchElementException as e:
        return f"error: {e}"
    field.send_keys(text)
    if submit:
        field.send_keys(Keys.RETURN)
    return f"typed into {css_selector!r}"


@mcp.tool()
def list_dir(path: str = ".") -> str:
    """List files and folders at the given path (relative paths are resolved from the project root)."""
    target = _resolve_path(path)
    entries = os.listdir(target)
    return "\n".join(sorted(entries))


@mcp.tool()
def read_file(path: str, max_chars: int = 20000) -> str:
    """Read a text file's contents (relative paths are resolved from the project root)."""
    target = _resolve_path(path)
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_chars)


@mcp.tool()
def run_python(code: str, timeout: int = 30) -> str:
    """Execute a Python snippet in a subprocess and return stdout/stderr. Disabled unless MCP_ALLOW_EXEC=1."""
    if not EXEC_ENABLED:
        return "error: run_python is disabled (set MCP_ALLOW_EXEC=1 in the environment to enable)"
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"error: timed out after {timeout}s"
    return f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


@mcp.tool()
def run_shell(command: str, timeout: int = 30) -> str:
    """Execute a shell command and return stdout/stderr. Disabled unless MCP_ALLOW_EXEC=1."""
    if not EXEC_ENABLED:
        return "error: run_shell is disabled (set MCP_ALLOW_EXEC=1 in the environment to enable)"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"error: timed out after {timeout}s"
    return f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


if __name__ == "__main__":
    mcp.run()
