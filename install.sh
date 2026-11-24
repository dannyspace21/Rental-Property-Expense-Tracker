#!/usr/bin/env bash
# =============================================================================
#  Rental Tracker - direct install for Linux (no Docker)
# =============================================================================
#  Sets the app up in this folder and starts it automatically on boot.
#
#    ./install.sh               install, or update after a "git pull"
#    ./install.sh --no-service  install only; you start it yourself
#    ./install.sh --uninstall   stop it and remove the background service
#                               (your data folder is kept)
#    ./install.sh --print-service  show the startup (systemd) file it would install
#
#  Your data stays in ./data, the same as with Docker.
#  Settings (port, property name, time zone) live in ./rental-tracker.env
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE=rental-tracker
UNIT="/etc/systemd/system/${SERVICE}.service"
ENV_FILE="$APP_DIR/rental-tracker.env"
VENV="$APP_DIR/.venv"
RUN_USER="${SUDO_USER:-$(id -un)}"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mNote:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }
have_systemd() { command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; }

service_file() {
cat <<EOF
[Unit]
Description=Rental Tracker
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/gunicorn --bind 0.0.0.0:\${PORT} --workers 1 app:app
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF
}

MODE=install
case "${1:-}" in
  ""|--install) ;;
  --no-service) MODE=no-service ;;
  --uninstall)  MODE=uninstall ;;
  --print-service) MODE=print ;;
  -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
  *) die "Unknown option '$1'. Try: ./install.sh --help" ;;
esac

if [ "$MODE" = print ]; then service_file; exit 0; fi

# ---------- uninstall ----------
if [ "$MODE" = uninstall ]; then
  if have_systemd && [ -f "$UNIT" ]; then
    say "Stopping and removing the $SERVICE service"
    as_root systemctl disable --now "$SERVICE" || true
    as_root rm -f "$UNIT"
    as_root systemctl daemon-reload
  else
    say "No $SERVICE service is installed."
  fi
  echo "Your data in $APP_DIR/data was kept. Delete the folder yourself if you no longer need it."
  exit 0
fi

# ---------- checks ----------
[ "$(id -u)" -eq 0 ] && [ -z "${SUDO_USER:-}" ] && \
  warn "Running as root. The app will run as root too; installing from a normal user account is safer."
command -v python3 >/dev/null 2>&1 || die "Python 3 is not installed. On Debian/Ubuntu/Raspberry Pi OS: sudo apt install python3 python3-venv"
python3 - <<'PY' || die "Python 3.9 or newer is required (found $(python3 --version 2>&1))."
import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)
PY
python3 -c "import venv, ensurepip" 2>/dev/null || \
  die "Python's venv module is missing. On Debian/Ubuntu/Raspberry Pi OS: sudo apt install python3-venv"

# ---------- settings file (created once, never overwritten) ----------
if [ ! -f "$ENV_FILE" ]; then
  NAME="My Rental Property"
  if [ -t 0 ]; then
    read -r -p "Name of your rental property [My Rental Property]: " ANSWER || true
    NAME="${ANSWER:-$NAME}"
  fi
  say "Creating settings file rental-tracker.env"
  cat > "$ENV_FILE" <<EOF
# Rental Tracker settings. After changing anything here, run:  ./install.sh
PORT=8090
# Name of your first property (only used the very first time; rename it later in the app)
PROPERTY_NAME=$NAME
# How many daily automatic backups to keep in data/backups (0 turns them off)
KEEP_BACKUPS=14
# Time zone for "today" and rent due dates. Leave commented out to use this computer's time zone.
#TZ=America/New_York
EOF
  if [ -n "${SUDO_USER:-}" ]; then chown "$RUN_USER" "$ENV_FILE"; fi
fi
PORT="$(sed -n 's/^[[:space:]]*PORT[[:space:]]*=[[:space:]]*//p' "$ENV_FILE" | tail -1 | tr -d "\"' \r")"; PORT="${PORT:-8090}"
[[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || die "PORT in rental-tracker.env must be a number (found '$PORT')."
[ "$PORT" -lt 1024 ] && warn "Ports below 1024 need root. Pick 1024 or higher (default 8090)."

# ---------- Python environment ----------
say "Setting up the app's Python environment in .venv (takes a minute the first time)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$APP_DIR/requirements.txt"
mkdir -p "$APP_DIR/data"

# Quick self-check in a throwaway folder: can the app load and create a database?
CHECK_DIR="$(mktemp -d)"
( cd "$APP_DIR" && DATA_DIR="$CHECK_DIR" "$VENV/bin/python" -c "import app" ) \
  || { rm -rf "$CHECK_DIR"; die "The app failed to start its self-check. See the error above."; }
rm -rf "$CHECK_DIR" "$APP_DIR/__pycache__"
if [ -n "${SUDO_USER:-}" ]; then chown -R "$RUN_USER" "$VENV" "$APP_DIR/data"; fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-<this-computer-ip>}"

if [ "$MODE" = no-service ] || ! have_systemd; then
  have_systemd || warn "systemd was not found, so the app can't be set up to start on boot."
  say "Installed. Start the app with:"
  echo "    cd \"$APP_DIR\" && .venv/bin/gunicorn --bind 0.0.0.0:$PORT --workers 1 app:app"
  echo "Then open http://$IP:$PORT"
  exit 0
fi

# ---------- background service (starts on boot, restarts if it crashes) ----------
if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$PORT" | grep -q LISTEN \
   && ! systemctl is-active --quiet "$SERVICE"; then
  warn "Something else is already using port $PORT. Change PORT in rental-tracker.env, then run ./install.sh again."
fi
say "Installing the $SERVICE service (asks for your password)"
TMP_UNIT="$(mktemp)"
service_file > "$TMP_UNIT"
as_root install -m 0644 "$TMP_UNIT" "$UNIT"
rm -f "$TMP_UNIT"
as_root systemctl daemon-reload
as_root systemctl enable "$SERVICE" >/dev/null 2>&1
as_root systemctl restart "$SERVICE"
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
  say "Done! Rental Tracker is running and will start automatically on boot."
  echo "    Open:    http://$IP:$PORT"
  echo "    Status:  systemctl status $SERVICE"
  echo "    Logs:    journalctl -u $SERVICE -n 50"
  echo "    Update:  git pull && ./install.sh"
else
  die "The service didn't start. See why with:  journalctl -u $SERVICE -n 50"
fi
