"""WATCHDOG V1 -- study-mode switch.

Toggling study mode ON runs `~/govee/mood study` on the NUC over SSH and starts a
stopwatch; OFF runs `~/govee/mood relax` and stops it. While studying, the apps
in blocker.BLOCKED (currently VS Code) are closed whenever they open.

Phone: each toggle also writes ~/watchdog/public/state.json on the NUC (same SSH
session); the WATCHDOG phone app (watchdog_phone/) polls it through the NUC's
signal server (nuc/serve.py) and locks the phone while studying.

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

from blocker import Blocker

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


# The phone app polls this file (served from the NUC by watchdog_app/nuc/serve.py).
SIGNAL_DIR = "~/watchdog/public"


def _exec(client, command):
    _, stdout, stderr = client.exec_command(command, timeout=30)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    code = stdout.channel.recv_exit_status()
    return code, (err or out or f"exit code {code}").splitlines()[-1][:120] if code else ""


def run_remote(mode=None, signal=None):
    """One SSH session to the NUC: write the phone signal (if given) first, so the
    phone locks even if the lights fail, then run the mood script (if mode given).
    Returns {"lights": (ok, msg), "phone": (ok, msg)} for whichever ran."""
    result = {}
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
            if signal is not None:
                body = json.dumps(signal)  # only numbers/bools: safe inside single quotes
                code, err = _exec(client, f"mkdir -p {SIGNAL_DIR} && printf '%s' '{body}' > {SIGNAL_DIR}/state.json.tmp"
                                          f" && mv {SIGNAL_DIR}/state.json.tmp {SIGNAL_DIR}/state.json")
                result["phone"] = (code == 0, "lock signal sent" if code == 0 else err)
            if mode is not None:
                code, err = _exec(client, MOOD_CMD.format(mode))
                result["lights"] = (code == 0, f"{user}@{host} :: mood {mode}" if code == 0 else err)
        finally:
            client.close()
    except Exception as exc:  # network down, NUC asleep, bad password...
        msg = f"{type(exc).__name__}: {exc}"[:160]
        if signal is not None:
            result.setdefault("phone", (False, msg))
        if mode is not None:
            result.setdefault("lights", (False, msg))
    return result


def run_mood(mode):
    """Lights only. Returns (ok, message)."""
    return run_remote(mode=mode)["lights"]


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
        self._phone = {"ok": None, "message": "idle", "busy": False}
        self._window = None
        self._blocker = Blocker()
        if self._state["studying"]:
            self._blocker.start()  # reopened mid-session: keep blocking

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
            "phone": dict(self._phone),
            "apps": self._blocker.status(),
        }

    def _signal(self):
        s = self._state
        return {"studying": bool(s["studying"]), "started_at": s["started_at"], "updated": time.time()}

    def _set_lights(self, mode, phone=True):
        """Push the phone signal + lights in one SSH session (background thread)."""
        self._lights = {"ok": None, "message": f"mood {mode} ...", "busy": True}
        if phone:
            self._phone = {"ok": None, "message": "sending ...", "busy": True}
        res = run_remote(mode=mode, signal=self._signal() if phone else None)
        ok, msg = res["lights"]
        self._lights = {"ok": ok, "message": msg, "busy": False}
        if phone:
            ok, msg = res["phone"]
            self._phone = {"ok": ok, "message": msg, "busy": False}

    def _push_phone(self):
        self._phone = {"ok": None, "message": "sending ...", "busy": True}
        ok, msg = run_remote(signal=self._signal())["phone"]
        self._phone = {"ok": ok, "message": msg, "busy": False}

    # -- API ---------------------------------------------------------------
    def get_state(self):
        return self._snapshot()

    def toggle(self):
        with self._lock:
            s = self._state
            if not s["studying"]:
                s["studying"], s["started_at"] = True, time.time()
                mode = "study"
                self._blocker.start()
            else:
                elapsed = int(time.time() - (s["started_at"] or time.time()))
                s["last_session"] = elapsed
                day = self._today_key()
                s["today"] = {day: s["today"].get(day, 0) + elapsed}  # keep only today
                s["studying"], s["started_at"] = False, None
                mode = "relax"
                self._blocker.stop()
            _save_state(s)
        # SSH can take seconds -- never block the UI on it
        threading.Thread(target=self._set_lights, args=(mode,), daemon=True).start()
        return self._snapshot()

    def reset_today(self):
        """Zero today's study total. Mid-session, the running stopwatch restarts
        from 0 too (otherwise it would add straight back into TODAY)."""
        with self._lock:
            s = self._state
            s["today"] = {self._today_key(): 0}
            if s["studying"]:
                s["started_at"] = time.time()
                # the phone's lock screen shows the session timer: keep it in sync
                threading.Thread(target=self._push_phone, daemon=True).start()
            _save_state(s)
        return self._snapshot()

    def retry_lights(self):
        mode = "study" if self._state["studying"] else "relax"
        threading.Thread(target=self._set_lights, args=(mode,), daemon=True).start()
        return self._snapshot()

    def retry_phone(self):
        threading.Thread(target=self._push_phone, daemon=True).start()
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
        # SW_RESTORE brings a minimized window back to fullscreen, but would
        # un-maximize a visible one -- so only use it when minimized.
        u32.ShowWindow(hwnd, 9 if u32.IsIconic(hwnd) else 5)  # SW_RESTORE / SW_SHOW
        u32.SetForegroundWindow(hwnd)
    return False


def _second_screen():
    """The first monitor that isn't the primary one (primary sits at 0,0)."""
    others = [s for s in webview.screens if (s.x, s.y) != (0, 0)]
    return others[0] if others else None


def _no_second_monitor():
    msg = "WATCHDOG runs fullscreen on your second monitor.\n\nConnect a second display and open it again."
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "WATCHDOG", 0x30)  # MB_ICONWARNING
    else:
        print(msg, file=sys.stderr)


def _pin_to_screen(window, bounds):
    """Keep the window fullscreen on its monitor: snap back if it is moved to
    another one (drag, Win+Shift+Arrow), close if that monitor is unplugged.
    Study state is saved, so closing never loses the stopwatch."""
    from System import Action
    from System.Windows import Forms as WinForms

    form = window.native
    device_name = None

    def check():
        nonlocal device_name
        if device_name is None:
            # pywebview only gives us the monitor's bounds; find its device name
            match = [s for s in WinForms.Screen.AllScreens if s.Bounds.Equals(bounds)]
            device_name = (match[0] if match else WinForms.Screen.FromControl(form)).DeviceName
        screens = {s.DeviceName: s for s in WinForms.Screen.AllScreens}
        target = screens.get(device_name)
        if target is None:
            form.Close()
            return
        if WinForms.Screen.FromControl(form).DeviceName != device_name:
            form.WindowState = WinForms.FormWindowState.Normal
            form.Bounds = target.Bounds
            form.WindowState = WinForms.FormWindowState.Maximized

    def on_moved(*_):
        try:
            form.BeginInvoke(Action(check))
        except Exception:
            pass

    window.events.moved += on_moved
    on_moved()  # record which monitor we're on now
    # display added/removed or rearranged
    from Microsoft.Win32 import SystemEvents
    SystemEvents.DisplaySettingsChanged += lambda *_: on_moved()


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
    screen = _second_screen()
    if screen is None:
        _no_second_monitor()
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
        screen=screen, fullscreen=True,  # fullscreen on the monitor it's placed on
        width=980, height=620,
        frameless=True, easy_drag=False,
        background_color="#111111",
    )
    api._window = window
    window.events.shown += lambda: _apply_icon(window)
    if os.name == "nt":
        window.events.shown += lambda: _pin_to_screen(window, screen.frame)
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
