"""
Minimal Flask server that stores and serves recent screenshots, plus a small
installable web app (PWA) for viewing them on an iPhone.

Endpoints:
  GET  /                  - no auth; the web app shell (it asks for the key itself)
  GET  /health            - no auth, used for platform health checks
  POST /upload            - requires X-API-Key header; body = raw image bytes
  GET  /screenshot        - requires X-API-Key header; returns the latest image
  GET  /screenshots       - requires X-API-Key header; JSON list, newest first
  GET  /screenshots/<id>  - requires X-API-Key header; returns that image
  POST /screenshots/<id>/text - requires X-API-Key header; body = OCR text (UTF-8)

Images are kept in memory only (no disk persistence), capped at HISTORY_SIZE.
This relies on gunicorn running a single worker so every request sees the same
store. Auth is a single shared secret compared with a constant-time check to
avoid timing attacks.
"""
import hmac
import os
import time
import uuid
from collections import deque

from flask import Flask, Response, abort, jsonify, request, send_from_directory

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=None)

API_SECRET = os.environ.get("API_SECRET", "")
HISTORY_SIZE = max(1, int(os.environ.get("HISTORY_SIZE", "10")))
MAX_TEXT_BYTES = 256 * 1024

# In-memory store of recent screenshots, newest first.
_history = deque(maxlen=HISTORY_SIZE)


def _check_auth():
    if not API_SECRET:
        abort(500, description="Server is misconfigured: API_SECRET is not set.")
    provided = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided, API_SECRET):
        abort(401, description="Invalid or missing API key.")


def _image_response(entry):
    resp = Response(entry["bytes"], mimetype=entry["mimetype"])
    # Contents of a given id never change, but keep it out of shared caches.
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200


@app.route("/upload", methods=["POST"])
def upload():
    _check_auth()
    data = request.get_data()
    if not data:
        abort(400, description="No image data received.")
    entry = {
        "id": uuid.uuid4().hex,
        "bytes": data,
        "mimetype": request.headers.get("Content-Type", "image/png"),
        "uploaded_at": time.time(),
        "text": None,  # OCR text, filled in by a follow-up POST from the uploader
    }
    _history.appendleft(entry)
    return jsonify(status="ok", id=entry["id"], uploaded_at=entry["uploaded_at"]), 200


@app.route("/screenshot", methods=["GET"])
def screenshot():
    _check_auth()
    if not _history:
        abort(404, description="No screenshot has been uploaded yet.")
    entry = _history[0]
    return Response(entry["bytes"], mimetype=entry["mimetype"])


@app.route("/screenshots", methods=["GET"])
def list_screenshots():
    _check_auth()
    items = [
        {
            "id": e["id"],
            "mimetype": e["mimetype"],
            "uploaded_at": e["uploaded_at"],
            "size": len(e["bytes"]),
            "text": e["text"],
        }
        for e in _history
    ]
    resp = jsonify(screenshots=items)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/screenshots/<screenshot_id>", methods=["GET"])
def get_screenshot(screenshot_id):
    _check_auth()
    for entry in _history:
        if entry["id"] == screenshot_id:
            return _image_response(entry)
    abort(404, description="That screenshot is no longer available.")


@app.route("/screenshots/<screenshot_id>/text", methods=["POST"])
def set_screenshot_text(screenshot_id):
    _check_auth()
    data = request.get_data()
    if len(data) > MAX_TEXT_BYTES:
        abort(413, description="OCR text is too large.")
    for entry in _history:
        if entry["id"] == screenshot_id:
            entry["text"] = data.decode("utf-8", errors="replace")
            return jsonify(status="ok"), 200
    abort(404, description="That screenshot is no longer available.")


# --- Web app (PWA) -----------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    resp = send_from_directory(STATIC_DIR, "index.html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/<path:filename>", methods=["GET"])
def static_files(filename):
    mimetypes = {
        "manifest.webmanifest": "application/manifest+json",
        "icon-180.png": "image/png",
        "icon-512.png": "image/png",
    }
    if filename not in mimetypes:
        abort(404)
    return send_from_directory(STATIC_DIR, filename, mimetype=mimetypes[filename])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
