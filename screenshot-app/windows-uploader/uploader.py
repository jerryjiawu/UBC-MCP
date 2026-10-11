"""
Watches the Windows screenshots folder(s) and uploads new screenshots to the
cloud server the instant they appear, using filesystem change events
(watchdog) instead of fixed-interval polling. Designed to be left running in
the background, either via run_uploader.bat / register_startup_task.ps1, or
as a managed server inside mcp_manager.py (which launches this script with
the project root as its working directory, not this folder).
"""
import glob
import os
import sys
import threading
import time

import requests
from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Load this script's own .env regardless of the process's current working
# directory (mcp_manager.py launches it with cwd=PROJECT_ROOT).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def log(message):
    print(message, flush=True)


def _screenshot_directories():
    """Return the Windows screenshot folder(s) to watch. OneDrive silently
    redirects Pictures (and therefore Pictures\\Screenshots) for a lot of
    setups, so check both the OneDrive-redirected path and the plain default
    rather than guessing one -- same approach already used elsewhere in this
    project (see discord_bot.py's screenshot watcher)."""
    home = os.path.expanduser("~")
    explicit = os.environ.get("SCREENSHOT_DIR")
    if explicit:
        return [os.path.normpath(explicit)]

    onedrive = os.environ.get("OneDrive") or os.path.join(home, "OneDrive")
    candidates = [
        os.path.join(onedrive, "Pictures", "Screenshots"),
        os.path.join(home, "Pictures", "Screenshots"),
    ]
    seen = set()
    directories = []
    for candidate in candidates:
        normalized = os.path.normpath(candidate)
        if normalized not in seen:
            seen.add(normalized)
            directories.append(normalized)
    return directories


SERVER_URL = os.environ.get("SERVER_URL", "").rstrip("/")
API_SECRET = os.environ.get("API_SECRET", "")
SCREENSHOT_DIRS = _screenshot_directories()
# Only used to notice a screenshot folder that didn't exist yet appearing for
# the first time (e.g. before you've ever taken a screenshot). New files in
# an already-watched folder are picked up instantly via filesystem events,
# not by this interval.
DIR_CHECK_SECONDS = float(os.environ.get("DIR_CHECK_SECONDS", "5"))
# Screenshot tools can still have the file open for a brief moment after the
# create/write event fires, so give it a beat and retry a few times instead
# of failing outright on a sharing violation.
UPLOAD_DEBOUNCE_SECONDS = 0.3

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
MIMETYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def find_latest_screenshot():
    paths = []
    for directory in SCREENSHOT_DIRS:
        if not os.path.isdir(directory):
            continue
        for ext in IMAGE_EXTENSIONS:
            paths.extend(glob.glob(os.path.join(directory, f"*{ext}")))
    if not paths:
        return None
    return max(paths, key=os.path.getmtime)


def _read_file_with_retry(path, attempts=10, delay=0.2):
    last_error = None
    for _ in range(attempts):
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError as e:
            last_error = e
            time.sleep(delay)
    raise last_error


class UploadScheduler:
    """Debounces rapid-fire filesystem events (create + several modifies as
    the screenshot tool writes the file) into a single upload of whatever is
    currently the newest screenshot."""

    def __init__(self):
        self._last_uploaded = None
        self._timer = None
        self._lock = threading.Lock()

    def notify(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(UPLOAD_DEBOUNCE_SECONDS, self._upload_latest)
            self._timer.daemon = True
            self._timer.start()

    def _upload_latest(self):
        latest = find_latest_screenshot()
        if not latest or latest == self._last_uploaded:
            return
        try:
            self._upload(latest)
            self._last_uploaded = latest
        except Exception as e:
            log(f"[error] {e}")

    def _upload(self, path):
        ext = os.path.splitext(path)[1].lower()
        mimetype = MIMETYPES.get(ext, "application/octet-stream")
        data = _read_file_with_retry(path)

        resp = requests.post(
            f"{SERVER_URL}/upload",
            data=data,
            headers={"X-API-Key": API_SECRET, "Content-Type": mimetype},
            timeout=15,
        )
        resp.raise_for_status()
        log(f"[uploaded] {os.path.basename(path)} -> {SERVER_URL}/upload ({resp.status_code})")


class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, scheduler):
        self._scheduler = scheduler

    def on_created(self, event):
        if not event.is_directory:
            self._scheduler.notify(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._scheduler.notify(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._scheduler.notify(event.dest_path)


def main():
    if not SERVER_URL or not API_SECRET:
        log("ERROR: SERVER_URL and API_SECRET must be set (see .env.example).")
        sys.exit(1)

    scheduler = UploadScheduler()
    observer = Observer()
    handler = ScreenshotHandler(scheduler)
    watched = set()

    def watch_if_exists(directory):
        if directory in watched or not os.path.isdir(directory):
            return
        observer.schedule(handler, directory, recursive=False)
        watched.add(directory)
        log(f"[watching] {directory}")

    for directory in SCREENSHOT_DIRS:
        watch_if_exists(directory)

    # Upload whatever screenshot already exists on startup (e.g. after an
    # uploader/server restart), then rely on events for anything new.
    existing = find_latest_screenshot()
    if existing:
        scheduler.notify(existing)

    observer.start()
    log("Watching for new screenshots (instant, event-driven)... (Ctrl+C to stop)")

    try:
        while True:
            time.sleep(DIR_CHECK_SECONDS)
            # Win+PrtScn only creates the folder the first time it's used,
            # so pick up a folder that has since appeared.
            for directory in SCREENSHOT_DIRS:
                if directory not in watched:
                    watch_if_exists(directory)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
