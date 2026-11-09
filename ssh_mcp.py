"""MCP server that runs commands and moves files on one remote host over SSH.

Configure in .env (or from the MCP Mommy dashboard's "SSH" panel, which writes
the same keys):

    SSH_HOST=example.com
    SSH_PORT=22
    SSH_USERNAME=me
    SSH_PASSWORD=secret

.env is re-read on every new connection, so changing the settings takes effect
on the next tool call without restarting the client.

Host keys are trust-on-first-use: the first key seen for a host is saved to
.ssh_known_hosts (gitignored), and any later mismatch is refused rather than
silently accepted. Delete the host's line from that file if the server's key
legitimately changed.
"""
import os
import posixpath
import stat
import threading

import paramiko
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
KNOWN_HOSTS = os.path.join(PROJECT_ROOT, ".ssh_known_hosts")

MAX_OUTPUT = 50_000  # chars returned per stream, so huge outputs don't flood the client
MAX_READ = 1_000_000  # bytes read_file will return

mcp = FastMCP("ssh-mcp")

_lock = threading.Lock()
_client = None
_client_key = None  # (host, port, user, password) the open client was made with


def _config():
    load_dotenv(ENV_PATH, override=True)
    host = os.getenv("SSH_HOST", "").strip()
    user = os.getenv("SSH_USERNAME", "").strip()
    password = os.getenv("SSH_PASSWORD", "")
    try:
        port = int(os.getenv("SSH_PORT", "22") or 22)
    except ValueError:
        port = 22
    if not host or not user:
        raise RuntimeError(
            "SSH is not configured. Set SSH_HOST, SSH_USERNAME and SSH_PASSWORD "
            "in .env or from the MCP Mommy dashboard."
        )
    return host, port, user, password


def _get_client():
    global _client, _client_key
    key = _config()
    with _lock:
        transport = _client.get_transport() if _client else None
        if _client and _client_key == key and transport and transport.is_active():
            return _client
        if _client:
            _client.close()
        host, port, user, password = key
        client = paramiko.SSHClient()
        if os.path.exists(KNOWN_HOSTS):
            client.load_host_keys(KNOWN_HOSTS)
        # Unknown host -> remember its key. Known host with a different key ->
        # paramiko raises BadHostKeyException regardless of this policy.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            host, port=port, username=user, password=password or None,
            look_for_keys=not password, allow_agent=not password, timeout=15,
        )
        client.save_host_keys(KNOWN_HOSTS)
        _client, _client_key = client, key
        return client


def _trim(text):
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT] + f"\n... [truncated {len(text) - MAX_OUTPUT} chars]"
    return text


@mcp.tool()
def ssh_run(command: str, timeout_seconds: int = 60) -> str:
    """Run a shell command on the configured SSH host and return exit code,
    stdout and stderr."""
    client = _get_client()
    _, stdout, stderr = client.exec_command(command, timeout=timeout_seconds)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return f"exit code: {code}\n--- stdout ---\n{_trim(out)}\n--- stderr ---\n{_trim(err)}"


@mcp.tool()
def ssh_list_dir(path: str = ".") -> str:
    """List a directory on the SSH host (name, size, type)."""
    sftp = _get_client().open_sftp()
    try:
        lines = []
        for entry in sorted(sftp.listdir_attr(path), key=lambda e: e.filename):
            kind = "d" if stat.S_ISDIR(entry.st_mode or 0) else "-"
            lines.append(f"{kind} {entry.st_size or 0:>12}  {entry.filename}")
        return "\n".join(lines) or "(empty)"
    finally:
        sftp.close()


@mcp.tool()
def ssh_read_file(path: str) -> str:
    """Read a text file from the SSH host (up to 1 MB)."""
    sftp = _get_client().open_sftp()
    try:
        with sftp.open(path, "rb") as fh:
            data = fh.read(MAX_READ + 1)
    finally:
        sftp.close()
    text = data[:MAX_READ].decode("utf-8", "replace")
    if len(data) > MAX_READ:
        text += "\n... [truncated at 1 MB]"
    return text


@mcp.tool()
def ssh_write_file(path: str, content: str) -> str:
    """Write (overwrite) a text file on the SSH host."""
    sftp = _get_client().open_sftp()
    try:
        with sftp.open(path, "wb") as fh:
            fh.write(content.encode("utf-8"))
    finally:
        sftp.close()
    return f"wrote {len(content)} chars to {path}"


@mcp.tool()
def ssh_upload(local_path: str, remote_path: str) -> str:
    """Copy a file from this computer to the SSH host. If remote_path ends in
    '/', the local file name is kept."""
    if remote_path.endswith("/"):
        remote_path = posixpath.join(remote_path, os.path.basename(local_path))
    sftp = _get_client().open_sftp()
    try:
        sftp.put(local_path, remote_path)
    finally:
        sftp.close()
    return f"uploaded {local_path} -> {remote_path}"


@mcp.tool()
def ssh_download(remote_path: str, local_path: str) -> str:
    """Copy a file from the SSH host to this computer."""
    sftp = _get_client().open_sftp()
    try:
        sftp.get(remote_path, local_path)
    finally:
        sftp.close()
    return f"downloaded {remote_path} -> {local_path}"


@mcp.tool()
def ssh_info() -> str:
    """Show which host/user is configured and whether the connection works."""
    host, port, user, _ = _config()
    try:
        client = _get_client()
        _, stdout, _ = client.exec_command("uname -a 2>/dev/null || ver", timeout=15)
        remote = stdout.read().decode("utf-8", "replace").strip()
        return f"connected to {user}@{host}:{port}\n{remote}"
    except Exception as exc:
        return f"configured {user}@{host}:{port} but connection failed: {exc}"


if __name__ == "__main__":
    mcp.run()
