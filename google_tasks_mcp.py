"""MCP server exposing Google Tasks to agents (list/create/complete/delete tasks).

First-time setup requires an interactive browser sign-in, which can't happen inside
a normal MCP tool call. Run this once before connecting an MCP client:

    python google_tasks_mcp.py --auth

That opens a browser for Google's OAuth consent screen and saves a refresh token to
google_token.json (gitignored). After that, run the server normally (no args) and it
will refresh the token silently.
"""
import os
import sys

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(PROJECT_ROOT, "google_token.json")

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SCOPES = ["https://www.googleapis.com/auth/tasks"]

CLIENT_CONFIG = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

mcp = FastMCP("google-tasks-mcp")

_service = None


def _load_credentials():
    if not os.path.exists(TOKEN_FILE):
        return None
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def _get_service():
    global _service
    if _service is not None:
        return _service
    creds = _load_credentials()
    if not creds or not creds.valid:
        raise RuntimeError(
            "Not authenticated with Google Tasks. Run "
            "'python google_tasks_mcp.py --auth' once to sign in, then restart this server."
        )
    _service = build("tasks", "v1", credentials=creds)
    return _service


def _run_auth_flow():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("error: set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first")
        return
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print(f"saved credentials to {TOKEN_FILE}")


@mcp.tool()
def list_task_lists() -> str:
    """List the user's Google Tasks task lists (id and title)."""
    service = _get_service()
    result = service.tasklists().list(maxResults=100).execute()
    lines = [f"{tl['id']} -> {tl['title']}" for tl in result.get("items", [])]
    return "\n".join(lines) if lines else "no task lists found"


@mcp.tool()
def list_tasks(tasklist_id: str = "@default", show_completed: bool = False) -> str:
    """List tasks in a task list (default: the primary list)."""
    service = _get_service()
    result = service.tasks().list(
        tasklist=tasklist_id, showCompleted=show_completed, maxResults=100
    ).execute()
    lines = []
    for t in result.get("items", []):
        status = t.get("status", "needsAction")
        due = t.get("due", "")
        suffix = f" (due {due})" if due else ""
        lines.append(f"{t['id']} [{status}] {t['title']}{suffix}")
    return "\n".join(lines) if lines else "no tasks found"


@mcp.tool()
def create_task(title: str, notes: str = "", due: str = "", tasklist_id: str = "@default") -> str:
    """Create a new task. 'due' is an optional RFC3339 date/time string, e.g. '2026-09-25T00:00:00Z'."""
    service = _get_service()
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    task = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
    return f"created {task['id']} -> {task['title']}"


@mcp.tool()
def complete_task(task_id: str, tasklist_id: str = "@default") -> str:
    """Mark a task as completed."""
    service = _get_service()
    service.tasks().patch(tasklist=tasklist_id, task=task_id, body={"status": "completed"}).execute()
    return f"completed {task_id}"


@mcp.tool()
def delete_task(task_id: str, tasklist_id: str = "@default") -> str:
    """Delete a task."""
    service = _get_service()
    service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
    return f"deleted {task_id}"


if __name__ == "__main__":
    if "--auth" in sys.argv:
        _run_auth_flow()
    else:
        mcp.run()
