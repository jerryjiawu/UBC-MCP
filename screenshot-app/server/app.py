"""
Minimal Flask server that stores and serves the single "latest screenshot".

Endpoints:
  GET  /health      - no auth, used for platform health checks
  POST /upload       - requires X-API-Key header; body = raw image bytes
  GET  /screenshot    - requires X-API-Key header; returns the latest image

The image is kept in memory only (no disk persistence needed since we only
ever care about the most recent one). Auth is a single shared secret compared
with a constant-time check to avoid timing attacks.
"""
import hmac
import os
import time

from flask import Flask, Response, abort, jsonify, request

app = Flask(__name__)

API_SECRET = os.environ.get("API_SECRET", "")

# In-memory store for the latest screenshot.
_latest = {"bytes": None, "mimetype": "image/png", "uploaded_at": None}


def _check_auth():
    if not API_SECRET:
        abort(500, description="Server is misconfigured: API_SECRET is not set.")
    provided = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided, API_SECRET):
        abort(401, description="Invalid or missing API key.")


@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200


@app.route("/upload", methods=["POST"])
def upload():
    _check_auth()
    data = request.get_data()
    if not data:
        abort(400, description="No image data received.")
    mimetype = request.headers.get("Content-Type", "image/png")
    _latest["bytes"] = data
    _latest["mimetype"] = mimetype
    _latest["uploaded_at"] = time.time()
    return jsonify(status="ok", uploaded_at=_latest["uploaded_at"]), 200


@app.route("/screenshot", methods=["GET"])
def screenshot():
    _check_auth()
    if _latest["bytes"] is None:
        abort(404, description="No screenshot has been uploaded yet.")
    return Response(_latest["bytes"], mimetype=_latest["mimetype"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
