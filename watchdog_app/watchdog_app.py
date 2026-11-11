"""WATCHDOG V1 -- study-mode switch.

Toggling study mode ON runs `~/govee/mood study` on the NUC over SSH and starts a
stopwatch; OFF runs `~/govee/mood relax` and stops it. Later modules (phone
lockdown, app blocking) plug in as more "connectors" -- see MODULES in the UI.

SSH target comes from the project .env: WATCHDOG_SSH_HOST/PORT/USERNAME/PASSWORD
if set, otherwise the SSH_* settings MCP Mommy's dashboard already manages.

Study state (on/off + start time) is saved to %LOCALAPPDATA%\\Watchdog\\state.json,
so closing and reopening the app mid-session keeps the stopwatch running.
"""
import json
import os
import sys
import threading
import time

import paramiko
import webview
from dotenv import dotenv_values

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
# shared with ssh_mcp.py: trust-on-first-use host keys
KNOWN_HOSTS = os.path.join(PROJECT_ROOT, ".ssh_known_hosts")

STATE_DIR = os.path.join(os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "Watchdog")
STATE_PATH = os.path.join(STATE_DIR, "state.json")

MOOD_CMD = "~/govee/mood {}"
SSH_TIMEOUT = 10


def _ssh_config():
    env = dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

    def pick(key, default=""):
        return (env.get(f"WATCHDOG_{key}") or env.get(key) or default).strip()

    host, user = pick("SSH_HOST"), pick("SSH_USERNAME")
    if not host or not user:
        raise RuntimeError("no SSH host/user in .env (set them in MCP Mommy's SSH panel)")
    password = env.get("WATCHDOG_SSH_PASSWORD") or env.get("SSH_PASSWORD") or ""
    return host, int(pick("SSH_PORT", "22") or 22), user, password


def run_mood(mode):
    """Run the mood script on the NUC. Returns (ok, message)."""
    try:
        host, port, user, password = _ssh_config()
        client = paramiko.SSHClient()
        if os.path.exists(KNOWN_HOSTS):
            client.load_host_keys(KNOWN_HOSTS)
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(host, port=port, username=user, password=password or None,
                           look_for_keys=not password, allow_agent=not password,
                           timeout=SSH_TIMEOUT, banner_timeout=SSH_TIMEOUT, auth_timeout=SSH_TIMEOUT)
            client.save_host_keys(KNOWN_HOSTS)
            _, stdout, stderr = client.exec_command(MOOD_CMD.format(mode), timeout=30)
            out = stdout.read().decode("utf-8", "replace").strip()
            err = stderr.read().decode("utf-8", "replace").strip()
            code = stdout.channel.recv_exit_status()
        finally:
            client.close()
        if code != 0:
            return False, (err or out or f"exit code {code}").splitlines()[-1][:120]
        return True, f"{user}@{host} :: mood {mode}"
    except Exception as exc:  # network down, NUC asleep, bad password...
        return False, f"{type(exc).__name__}: {exc}"[:160]


def _load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"studying": False, "started_at": None, "last_session": 0, "today": {}}


def _save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_PATH)


class Api:
    """Methods callable from the page as window.pywebview.api.<name>()."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = _load_state()
        self._state.setdefault("today", {})
        self._lights = {"ok": None, "message": "idle", "busy": False}
        self._window = None

    # -- helpers -----------------------------------------------------------
    def _today_key(self):
        return time.strftime("%Y-%m-%d")

    def _snapshot(self):
        s = self._state
        return {
            "studying": s["studying"],
            "started_at": s["started_at"],
            "now": time.time(),
            "last_session": s.get("last_session", 0),
            "today_total": s["today"].get(self._today_key(), 0),
            "lights": dict(self._lights),
        }

    def _set_lights(self, mode):
        self._lights = {"ok": None, "message": f"mood {mode} ...", "busy": True}
        ok, msg = run_mood(mode)
        self._lights = {"ok": ok, "message": msg, "busy": False}

    # -- API ---------------------------------------------------------------
    def get_state(self):
        return self._snapshot()

    def toggle(self):
        with self._lock:
            s = self._state
            if not s["studying"]:
                s["studying"], s["started_at"] = True, time.time()
                mode = "study"
            else:
                elapsed = int(time.time() - (s["started_at"] or time.time()))
                s["last_session"] = elapsed
                day = self._today_key()
                s["today"] = {day: s["today"].get(day, 0) + elapsed}  # keep only today
                s["studying"], s["started_at"] = False, None
                mode = "relax"
            _save_state(s)
        # SSH can take seconds -- never block the UI on it
        threading.Thread(target=self._set_lights, args=(mode,), daemon=True).start()
        return self._snapshot()

    def retry_lights(self):
        mode = "study" if self._state["studying"] else "relax"
        threading.Thread(target=self._set_lights, args=(mode,), daemon=True).start()
        return self._snapshot()

    def minimize(self):
        self._window.minimize()

    def close(self):
        self._window.destroy()


ICON_PATH = os.path.join(APP_DIR, "watchdog.ico")
APP_ID = "jerry.watchdog.v1"


def _single_instance():
    """Return True if this is the only WATCHDOG running; otherwise focus the
    existing window and return False."""
    if os.name != "nt":
        return True
    import ctypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    _single_instance.handle = k32.CreateMutexW(None, False, "Local\\" + APP_ID)
    if k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return True
    hwnd = u32.FindWindowW(None, "WATCHDOG")
    if hwnd:
        u32.ShowWindow(hwnd, 9)  # SW_RESTORE
        u32.SetForegroundWindow(hwnd)
    return False


def _apply_icon(window):
    """pywebview's Windows backend ignores icon=, so set it on the WinForms form."""
    try:
        from System import Action
        from System.Drawing import Icon
        form = window.native
        form.Invoke(Action(lambda: setattr(form, "Icon", Icon(ICON_PATH))))
    except Exception:
        pass


def main():
    if not _single_instance():
        return
    if os.name == "nt":
        import ctypes
        # own taskbar group + icon instead of being lumped in with python.exe
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    api = Api()
    window = webview.create_window(
        "WATCHDOG",
        url=os.path.join(APP_DIR, "ui", "index.html"),
        js_api=api,
        width=980, height=620, min_size=(760, 560),
        frameless=True, easy_drag=False,
        background_color="#111111",
    )
    api._window = window
    window.events.shown += lambda: _apply_icon(window)
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
