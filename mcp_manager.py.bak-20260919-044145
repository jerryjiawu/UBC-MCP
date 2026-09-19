"""Local web dashboard to start/stop/monitor the MCP servers in this project.

SECURITY: binds to 127.0.0.1 only and has no authentication. It gives control over
starting/stopping/restarting local subprocesses -- do not expose it on a network
interface, do not add port forwarding, and do not run it on a shared machine.
"""
import atexit
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque

from flask import Flask, jsonify
from PIL import Image, ImageDraw
import pystray

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

_venv_python = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
PYTHON = _venv_python if os.path.exists(_venv_python) else sys.executable

SERVERS = {
    "ubc-mcp": os.path.join(PROJECT_ROOT, "mcp_server.py"),
    "google-tasks-mcp": os.path.join(PROJECT_ROOT, "google_tasks_mcp.py"),
}

LOG_LINES = 200


class ManagedServer:
    def __init__(self, name, script_path):
        self.name = name
        self.script_path = script_path
        self.process = None
        self.logs = deque(maxlen=LOG_LINES)
        self.started_at = None

    def start(self):
        if self.is_running():
            return
        self.process = subprocess.Popen(
            [PYTHON, self.script_path],
            cwd=PROJECT_ROOT,
            # stdio-transport MCP servers read from stdin; DEVNULL looks like an
            # immediately-closed client and makes them exit right away, so keep
            # stdin open (as a pipe we simply never write to) instead.
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.started_at = time.time()
        threading.Thread(target=self._read_logs, daemon=True).start()

    def _read_logs(self):
        proc = self.process
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            self.logs.append(line.rstrip())

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self.started_at = None

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def status(self):
        return {
            "name": self.name,
            "running": self.is_running(),
            "pid": self.process.pid if self.is_running() else None,
            "uptime": int(time.time() - self.started_at) if self.is_running() and self.started_at else 0,
            "logs": list(self.logs)[-50:],
        }


managed = {name: ManagedServer(name, path) for name, path in SERVERS.items()}


@atexit.register
def _stop_all():
    for srv in managed.values():
        srv.stop()


app = Flask(__name__)

INDEX_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>mcp-manager</title>
<style>
  :root {
    --bg: #0c0c0c;
    --fg: #d9d6cf;
    --dim: #6f6b64;
    --accent: #da7756;
    --ok: #7ec699;
    --bad: #e0685c;
    --rule: #3a3a3a;
  }
  * { box-sizing: border-box; }
  body {
    font-family: ui-monospace, Consolas, monospace;
    background: var(--bg);
    color: var(--fg);
    margin: 0;
    padding: 2rem;
    font-size: 14px;
  }
  pre.banner { color: var(--accent); margin: 0 0 1.5rem 0; line-height: 1.15; }
  .rule { color: var(--rule); white-space: pre; margin: 0; }
  .server { padding: 0.6rem 0; border-bottom: 1px dashed var(--rule); }
  .server:last-child { border-bottom: none; }
  .row { display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap; }
  .name { color: var(--fg); font-weight: bold; min-width: 18ch; }
  .tag.running { color: var(--ok); }
  .tag.stopped { color: var(--bad); }
  .meta { color: var(--dim); }
  .cmds a { color: var(--dim); text-decoration: none; cursor: pointer; margin-right: 1rem; }
  .cmds a:hover { color: var(--accent); text-decoration: underline; }
  .prompt { color: var(--accent); }
</style>
</head>
<body>
<pre class="banner"> __  __  ____ ____    __  __    _    _   _    _    ____ _____ ____
|  \/  |/ ___|  _ \  |  \/  |  / \  | \ | |  / \  / ___| ____|  _ \
| |\/| | |   | |_) | | |\/| | / _ \ |  \| | / _ \| |  _|  _| | |_) |
| |  | | |___|  __/  | |  | |/ ___ \| |\  |/ ___ \ |_| | |___|  _ &lt;
|_|  |_|\____|_|     |_|  |_/_/   \_\_| \_/_/   \_\____|_____|_| \_\</pre>
<p class="rule">------------------------------------------------------------------------</p>
<div id="servers"></div>
<p class="rule">------------------------------------------------------------------------</p>
<p class="meta"><span class="prompt">$</span> polling every 2s, 127.0.0.1 only, no auth</p>
<script>
async function act(name, action) {
  await fetch(`/api/${name}/${action}`, { method: 'POST' });
  refresh();
}

function render(data) {
  const root = document.getElementById('servers');
  root.innerHTML = '';
  for (const name in data) {
    const s = data[name];
    const div = document.createElement('div');
    div.className = 'server';
    const tag = s.running ? 'running' : 'stopped';
    const label = s.running ? `RUNNING pid=${s.pid} up=${s.uptime}s` : 'STOPPED';
    div.innerHTML = `
      <div class="row">
        <span class="name">${name}</span>
        <span class="tag ${tag}">[ ${label} ]</span>
      </div>
      <div class="row cmds">
        <a onclick="act('${name}','start')">start</a>
        <a onclick="act('${name}','stop')">stop</a>
        <a onclick="act('${name}','restart')">restart</a>
      </div>
    `;
    root.appendChild(div);
  }
}

async function refresh() {
  const res = await fetch('/api/status');
  render(await res.json());
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/api/status")
def api_status():
    return jsonify({name: srv.status() for name, srv in managed.items()})


@app.route("/api/<name>/start", methods=["POST"])
def api_start(name):
    if name not in managed:
        return jsonify({"error": "unknown server"}), 404
    managed[name].start()
    return jsonify(managed[name].status())


@app.route("/api/<name>/stop", methods=["POST"])
def api_stop(name):
    if name not in managed:
        return jsonify({"error": "unknown server"}), 404
    managed[name].stop()
    return jsonify(managed[name].status())


@app.route("/api/<name>/restart", methods=["POST"])
def api_restart(name):
    if name not in managed:
        return jsonify({"error": "unknown server"}), 404
    managed[name].stop()
    managed[name].start()
    return jsonify(managed[name].status())


if __name__ == "__main__":
    for srv in managed.values():
        srv.start()
    port = int(os.getenv("MCP_MANAGER_PORT", "5055"))
    url = f"http://127.0.0.1:{port}"

    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    ).start()

    def _tray_icon_image():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((2, 2, 61, 61), fill=(218, 119, 86, 255))
        draw.text((20, 18), "M", fill=(12, 12, 12, 255))
        return img

    def _on_open(icon, item):
        webbrowser.open(url)

    def _on_quit(icon, item):
        icon.stop()
        _stop_all()
        os._exit(0)

    tray = pystray.Icon(
        "mcp-manager",
        icon=_tray_icon_image(),
        title="MCP Manager",
        menu=pystray.Menu(
            pystray.MenuItem("Open Dashboard", _on_open, default=True),
            pystray.MenuItem("Quit", _on_quit),
        ),
    )
    tray.run()
