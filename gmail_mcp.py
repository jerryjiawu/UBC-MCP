"""MCP server exposing read-only Gmail access, restricted to a fixed sender allowlist.

Two layers of restriction, not just one:
  1. OAuth scope is gmail.readonly -- there is no send/modify/delete permission at all
     at the Google API level, even if this code had a bug.
  2. Every tool additionally filters to ALLOWED_SENDERS below. list_emails() only
     searches those senders, and read_email() re-checks the sender on the fetched
     message and refuses to return the body of anything else (defense in depth in
     case a message id from outside the allowlist is ever passed in).

First-time setup requires an interactive browser sign-in, which can't happen inside a
normal MCP tool call. Run this once before connecting an MCP client:

    python gmail_mcp.py --auth

That opens a browser for Google's OAuth consent screen and saves a refresh token to
gmail_token.json (gitignored). After that, run the server normally (no args) and it
will refresh the token silently.
"""
import base64
import os
import re
import sys

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(PROJECT_ROOT, "gmail_token.json")

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# The agent can only ever see mail from these addresses -- read-only, never send/modify.
ALLOWED_SENDERS = [
    "rover.ubc@gmail.com",
    "notifications@instructure.com",
    "financial.support@askme.ubc.ca",
]

CLIENT_CONFIG = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

mcp = FastMCP("gmail-mcp")

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
            "Not authenticated with Gmail. Run "
            "'python gmail_mcp.py --auth' once to sign in, then restart this server."
        )
    _service = build("gmail", "v1", credentials=creds)
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


def _sender_query() -> str:
    return "(" + " OR ".join(f"from:{addr}" for addr in ALLOWED_SENDERS) + ")"


def _extract_email(header_value: str) -> str:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", header_value or "")
    return match.group(0).lower() if match else ""


def _header(headers, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(payload) -> str:
    if not payload:
        return ""
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _decode_body(part)
        if text:
            return text
    return ""


@mcp.tool()
def list_allowed_senders() -> str:
    """List the email addresses this server is allowed to read mail from."""
    return "\n".join(ALLOWED_SENDERS)


@mcp.tool()
def list_emails(query: str = "", max_results: int = 10) -> str:
    """List recent emails from the allowed senders only. 'query' can add extra Gmail search terms (e.g. 'is:unread', 'subject:invoice') on top of the sender restriction."""
    service = _get_service()
    q = _sender_query()
    if query:
        q += f" {query}"
    result = service.users().messages().list(userId="me", q=q, maxResults=max_results).execute()
    ids = [m["id"] for m in result.get("messages", [])]
    if not ids:
        return "no matching emails"
    lines = []
    for mid in ids:
        msg = service.users().messages().get(
            userId="me", id=mid, format="metadata", metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        lines.append(f"{mid} | {_header(headers, 'Date')} | {_header(headers, 'From')} | {_header(headers, 'Subject')}")
    return "\n".join(lines)


@mcp.tool()
def read_email(message_id: str) -> str:
    """Read the full body of an email by id. Refuses if the message isn't from an allowed sender."""
    service = _get_service()
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = msg.get("payload", {}).get("headers", [])
    sender = _extract_email(_header(headers, "From"))
    if sender not in ALLOWED_SENDERS:
        return f"error: message {message_id} is not from an allowed sender -- refusing to read it"
    body = _decode_body(msg.get("payload"))
    return (
        f"From: {_header(headers, 'From')}\n"
        f"Subject: {_header(headers, 'Subject')}\n"
        f"Date: {_header(headers, 'Date')}\n\n"
        f"{body[:8000]}"
    )


if __name__ == "__main__":
    if "--auth" in sys.argv:
        _run_auth_flow()
    else:
        mcp.run()
