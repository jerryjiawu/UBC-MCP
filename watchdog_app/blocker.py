"""App blocker for study mode (Windows).

While active, any process in BLOCKED is closed: first politely (WM_CLOSE via
taskkill without /F, so VS Code quits normally and hot-exit backs up unsaved
files), then forcefully if it is still running after GRACE seconds.
"""
import csv
import io
import subprocess
import threading
import time

# display name -> process image name
BLOCKED = {"VS Code": "Code.exe"}

POLL = 1.5   # seconds between checks while studying
GRACE = 4.0  # seconds to let an app close itself before force-killing

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _running(image):
    """PIDs of running processes with this image name."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for row in csv.reader(io.StringIO(out)):
        if len(row) > 1 and row[0].lower() == image.lower():
            pids.append(int(row[1]))
    return pids


def _taskkill(image, force):
    args = ["taskkill", "/IM", image, "/T"] + (["/F"] if force else [])
    subprocess.run(args, capture_output=True, timeout=15, creationflags=_NO_WINDOW)


class Blocker:
    def __init__(self, blocked=None):
        self.blocked = dict(blocked or BLOCKED)
        self.blocks = 0          # times a blocked app was closed this session
        self.last = None         # display name of the last app closed
        self._stop = threading.Event()
        self._thread = None

    @property
    def active(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self):
        if self.active:
            return
        # Fresh stop event per session: a previous watcher that is still winding
        # down (quick off -> on) keeps its own, already-set event and just exits.
        self._stop = threading.Event()
        self.blocks, self.last = 0, None
        self._thread = threading.Thread(target=self._loop, args=(self._stop,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def status(self):
        return {"active": self.active, "apps": list(self.blocked), "blocks": self.blocks, "last": self.last}

    def _close(self, name, image, stop):
        _taskkill(image, force=False)
        deadline = time.time() + GRACE
        while time.time() < deadline and _running(image):
            if stop.wait(0.5):
                return  # study mode ended mid-close: leave it be
        if _running(image):
            _taskkill(image, force=True)
        self.blocks += 1
        self.last = name

    def _loop(self, stop):
        while not stop.is_set():
            for name, image in self.blocked.items():
                if stop.is_set():
                    break
                if _running(image):
                    self._close(name, image, stop)
            stop.wait(POLL)
