#!/usr/bin/env bash
# UBC MCP installer for Debian (and Debian-based) servers, including headless
# ones with no desktop.
#
# What it does (safe to re-run; every step is idempotent):
#   1. apt: Python, venv, build tools, git, curl, Chromium + chromedriver
#   2. .venv with CPU-only PyTorch (no multi-GB CUDA download) + requirements.txt
#   3. .env from .env.example if missing, plus headless/Chromium settings
#   4. Claude Code (official installer) if it isn't installed
#   5. Registers the MCP servers in Claude Code (user scope), and in a Claude
#      Desktop config too if one exists on this machine
#   6. systemd service "mcp-mommy" that runs MCP Mommy headless at boot
#
# Usage:  ./install-linux.sh [--no-apt] [--no-claude-code] [--no-service]
# Run it as the user that should own and run the services (not root); it uses
# sudo for the apt and systemd steps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
SERVICE=mcp-mommy
RUN_USER="$(id -un)"

DO_APT=1 DO_CLAUDE=1 DO_SERVICE=1
for arg in "$@"; do
  case "$arg" in
    --no-apt) DO_APT=0 ;;
    --no-claude-code) DO_CLAUDE=0 ;;
    --no-service) DO_SERVICE=0 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run this as your normal user, not root (it calls sudo itself).
       The services would otherwise run as root with full access to the machine."
[ "$(uname -s)" = "Linux" ] || die "this installer is for Linux; on Windows use MCP Mommy directly."
command -v apt-get >/dev/null || [ "$DO_APT" -eq 0 ] || die "apt-get not found (not Debian-based?). Install the packages yourself and pass --no-apt."

SUDO=sudo
command -v sudo >/dev/null || die "sudo is required (apt install sudo, and add $RUN_USER to the sudo group)."

# ---------------------------------------------------------------- 1. packages
if [ "$DO_APT" -eq 1 ]; then
  step "Installing system packages (apt)"
  $SUDO apt-get update -qq
  # chromium + chromium-driver: the UBC MCP drives a headless browser for CWL/Canvas.
  # fonts-liberation: pages render with real fonts instead of boxes.
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev build-essential \
    git curl ca-certificates chromium chromium-driver fonts-liberation >/dev/null
  note "done"
fi

command -v python3 >/dev/null || die "python3 not found"
python3 - <<'EOF' || die "Python 3.10 or newer is required"
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF

# ---------------------------------------------------------------- 2. venv
step "Setting up Python environment in .venv"
if [ -d "$VENV" ] && [ ! -x "$PY" ]; then
  # e.g. a .venv copied over from Windows (has Scripts/, no bin/) -- unusable here
  mv "$VENV" "$VENV.not-linux.$(date +%s)"
  note "moved an existing non-Linux .venv aside"
fi
[ -x "$PY" ] || python3 -m venv "$VENV"
"$PY" -m pip install -q --upgrade pip wheel
# sentence-transformers pulls in torch; the default Linux wheel bundles CUDA
# (several GB). A server without a GPU only needs the CPU build.
if ! "$PY" -c "import torch" 2>/dev/null; then
  note "installing CPU-only PyTorch (this is the slow part)"
  "$PY" -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu
fi
note "installing requirements.txt"
"$PY" -m pip install -q -r "$ROOT/requirements.txt"
note "done"

# ---------------------------------------------------------------- 3. .env
step "Configuring .env"
ENV_FILE="$ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  note "created .env from .env.example -- fill in your credentials (see the end of this output)"
fi
chmod 600 "$ENV_FILE"
# add KEY=VALUE only if KEY isn't already set, so re-runs never clobber your edits
env_default() {
  grep -q "^$1=" "$ENV_FILE" || printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
}
[ -n "$(tail -c1 "$ENV_FILE")" ] && echo >> "$ENV_FILE"
env_default SELENIUM_HEADLESS 1
env_default MCP_MOMMY_HEADLESS 1
[ -x /usr/bin/chromium ] && env_default CHROME_BINARY /usr/bin/chromium
[ -x /usr/bin/chromedriver ] && env_default CHROMEDRIVER /usr/bin/chromedriver
note "done (permissions 600)"

# ---------------------------------------------------------------- 4. Claude Code
export PATH="$HOME/.local/bin:$PATH"
if [ "$DO_CLAUDE" -eq 1 ] && ! command -v claude >/dev/null; then
  step "Installing Claude Code"
  curl -fsSL https://claude.ai/install.sh | bash
  command -v claude >/dev/null || die "Claude Code install finished but 'claude' is not on PATH"
fi

# ---------------------------------------------------------------- 5. MCP config
# name -> script; same set as the Windows Claude Desktop config
MCP_NAMES=(ubc-mcp google-tasks-mcp gmail-mcp prairie-practice ssh-mcp)
MCP_SCRIPTS=(mcp_server.py google_tasks_mcp.py gmail_mcp.py prairie_practice_mcp.py ssh_mcp.py)

if command -v claude >/dev/null; then
  step "Registering MCP servers with Claude Code (user scope)"
  for i in "${!MCP_NAMES[@]}"; do
    name="${MCP_NAMES[$i]}"
    claude mcp remove -s user "$name" >/dev/null 2>&1 || true
    claude mcp add -s user "$name" -- "$PY" "$ROOT/${MCP_SCRIPTS[$i]}" >/dev/null
    note "$name"
  done
  # The repo's .mcp.json holds Windows paths for prairie-practice. Project scope
  # beats user scope, so add a local-scope entry for this checkout that wins.
  (cd "$ROOT" && {
    claude mcp remove -s local prairie-practice >/dev/null 2>&1 || true
    claude mcp add -s local prairie-practice -- "$PY" "$ROOT/prairie_practice_mcp.py" >/dev/null
  })
  note "(plus a local override of the repo's Windows-only .mcp.json entry)"
else
  note "Claude Code not installed -- skipped (re-run without --no-claude-code to add it)"
fi

# Claude Desktop has no official Linux build, but if a config exists (community
# build, or a desktop Linux machine), merge the servers into it too.
DESKTOP_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude_desktop_config.json"
if [ -d "$(dirname "$DESKTOP_CFG")" ]; then
  step "Updating Claude Desktop config"
  [ -f "$DESKTOP_CFG" ] && cp "$DESKTOP_CFG" "$DESKTOP_CFG.bak-$(date +%Y%m%d-%H%M%S)"
  "$PY" - "$DESKTOP_CFG" "$PY" "$ROOT" "${MCP_NAMES[*]}" "${MCP_SCRIPTS[*]}" <<'EOF'
import json, os, sys
path, py, root, names, scripts = sys.argv[1:]
cfg = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
servers = cfg.setdefault("mcpServers", {})
for name, script in zip(names.split(), scripts.split()):
    servers[name] = {"command": py, "args": [os.path.join(root, script)]}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2)
print("    updated", path)
EOF
fi

# ---------------------------------------------------------------- 6. service
if [ "$DO_SERVICE" -eq 1 ]; then
  step "Installing systemd service '$SERVICE'"
  UNIT="/etc/systemd/system/$SERVICE.service"
  $SUDO tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=MCP Mommy - UBC MCP process supervisor (headless)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
Environment=MCP_MOMMY_HEADLESS=1
Environment=PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$PY $ROOT/mcp_manager.py --headless
# SIGTERM goes to MCP Mommy first so it can stop its children cleanly
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable "$SERVICE" >/dev/null 2>&1
  $SUDO systemctl restart "$SERVICE"
  sleep 3
  if systemctl is-active --quiet "$SERVICE"; then
    note "running; starts automatically at boot"
  else
    note "service failed to start -- check: journalctl -u $SERVICE -n 50"
  fi
fi

# ---------------------------------------------------------------- next steps
HOST="$(hostname -f 2>/dev/null || hostname)"
cat <<EOF

$(printf '\033[1;32m')Install complete.$(printf '\033[0m')

Next steps:
  1. Fill in credentials:   nano $ENV_FILE
     (CWL_USERNAME/PASSWORD, GOOGLE_CLIENT_ID/SECRET, DISCORD_BOT_TOKEN, GEMINI_API_KEY, SSH_*)
     then: sudo systemctl restart $SERVICE

  2. Google sign-in (Gmail + Tasks). Easiest: copy the tokens from your Windows PC:
       scp google_token.json gmail_token.json $RUN_USER@$HOST:$ROOT/
     Or sign in here -- the scripts print a URL and tell you which SSH tunnel to open:
       $PY $ROOT/google_tasks_mcp.py --auth
       $PY $ROOT/gmail_mcp.py --auth
     Also worth copying over: links.json and prairie_practice/data/ (your practice history).

  3. Claude Code login (works over SSH -- it prints a URL to open on your own computer):
       claude      then type /login

  4. MCP Mommy dashboard (local-only, no auth -- reach it through an SSH tunnel):
       ssh -L 5055:127.0.0.1:5055 $RUN_USER@$HOST     then open http://127.0.0.1:5055
     Logs:    journalctl -u $SERVICE -f
     Control: sudo systemctl {status|restart|stop} $SERVICE

  Notes: the Windows screenshot uploader is skipped on Linux. CWL Duo logins work by
  phone push only -- there is no screen here for Duo's in-browser steps.
EOF
