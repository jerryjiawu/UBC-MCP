"""
Watches the Windows screenshots folder and uploads the newest image to the
cloud server whenever it changes. Designed to be left running in the
background (see run_uploader.bat / register_startup_task.ps1).
"""
import glob
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = os.environ.get("SERVER_URL", "").rstrip("/")
API_SECRET = os.environ.get("API_SECRET", "")
SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR") or os.path.join(
    os.path.expanduser("~"), "Pictures", "Screenshots"
)
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "3"))

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
MIMETYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def find_latest_screenshot():
    paths = []
    for ext in IMAGE_EXTENSIONS:
        paths.extend(glob.glob(os.path.join(SCREENSHOT_DIR, f"*{ext}")))
    if not paths:
        return None
    return max(paths, key=os.path.getmtime)


def upload(path):
    ext = os.path.splitext(path)[1].lower()
    mimetype = MIMETYPES.get(ext, "application/octet-stream")

    with open(path, "rb") as f:
        data = f.read()

    resp = requests.post(
        f"{SERVER_URL}/upload",
        data=data,
        headers={"X-API-Key": API_SECRET, "Content-Type": mimetype},
        timeout=15,
    )
    resp.raise_for_status()
    print(f"[uploaded] {os.path.basename(path)} -> {SERVER_URL}/upload ({resp.status_code})")


def main():
    if not SERVER_URL or not API_SECRET:
        print("ERROR: SERVER_URL and API_SECRET must be set (see .env.example).")
        sys.exit(1)

    if not os.path.isdir(SCREENSHOT_DIR):
        print(f"ERROR: Screenshot folder not found: {SCREENSHOT_DIR}")
        sys.exit(1)

    print(f"Watching {SCREENSHOT_DIR} for new screenshots... (Ctrl+C to stop)")
    last_uploaded = None
    while True:
        try:
            latest = find_latest_screenshot()
            if latest and latest != last_uploaded:
                upload(latest)
                last_uploaded = latest
        except Exception as e:
            print(f"[error] {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
