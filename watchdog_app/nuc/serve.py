#!/usr/bin/env python3
"""WATCHDOG signal server (runs on the NUC).

Serves ~/watchdog/public read-only on port 8787. The PC's WATCHDOG app writes
state.json there over SSH on every study-mode toggle, and the phone app polls it.
Nothing else in the home directory is reachable, and there are no directory
listings. Installed by install_signal_server.sh.
"""
import functools
import http.server
import os

ROOT = os.path.expanduser("~/watchdog/public")
PORT = int(os.environ.get("WATCHDOG_PORT", "8787"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def list_directory(self, path):  # no directory listings
        self.send_error(404)
        return None

    def log_message(self, *args):  # quiet: the phone polls every few seconds
        pass


if __name__ == "__main__":
    os.makedirs(ROOT, exist_ok=True)
    http.server.ThreadingHTTPServer(
        ("0.0.0.0", PORT), functools.partial(Handler, directory=ROOT)
    ).serve_forever()
