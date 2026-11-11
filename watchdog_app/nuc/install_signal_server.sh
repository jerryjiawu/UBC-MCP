#!/bin/sh
# Starts the WATCHDOG signal server on the NUC and keeps it running across reboots.
# Run it on the NUC from this folder (or have Claude run it over SSH once you approve).
#   - copies serve.py to ~/watchdog/serve.py
#   - adds ONE line to your crontab:  @reboot python3 ~/watchdog/serve.py
#   - starts it now on port 8787 (serves only ~/watchdog/public, read-only)
# Undo:  crontab -l | grep -v watchdog/serve.py | crontab - ; pkill -f watchdog/serve.py
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/watchdog/public"
cp "$HERE/serve.py" "$HOME/watchdog/serve.py"
[ -f "$HOME/watchdog/public/state.json" ] || echo '{"studying": false, "started_at": null, "updated": 0}' > "$HOME/watchdog/public/state.json"
# (`|| true`: with an empty crontab grep matches nothing and exits 1, which set -e
#  would otherwise treat as fatal and install an empty crontab)
{ crontab -l 2>/dev/null | grep -v 'watchdog/serve.py' || true; echo "@reboot /usr/bin/python3 $HOME/watchdog/serve.py >/dev/null 2>&1"; } | crontab -
pkill -f 'watchdog/serve.py' 2>/dev/null || true
nohup /usr/bin/python3 "$HOME/watchdog/serve.py" >/dev/null 2>&1 &
sleep 1
curl -fsS http://127.0.0.1:8787/state.json && echo && echo "signal server running on :8787"
