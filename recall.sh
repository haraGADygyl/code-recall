#!/bin/bash

umask 077

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# Load the optional extra PATH if .env exists
if [ -z "${EXTRA_PATH:-}" ] && [ -f .env ]; then
    # Avoid sourcing .env because it may contain values that are not shell-safe.
    EXTRA_PATH=$(grep -m1 '^EXTRA_PATH=' .env | cut -d'=' -f2- | tr -d '"')
fi

# Set up PATH - includes user local bin and any extra paths from .env
export PATH="${EXTRA_PATH:+$EXTRA_PATH:}$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/code-recall"
mkdir -p -m 700 "$STATE_DIR" || exit 1
chmod 700 "$STATE_DIR"
LOG_FILE="$STATE_DIR/recall-error.log"
LOCK_FILE="$STATE_DIR/recall.lock"

log_error() {
    printf '%s ERROR: %s\n' "$(date --iso-8601=seconds)" "$1" >> "$LOG_FILE"
}

exec 9> "$LOCK_FILE"
if ! command -v flock > /dev/null; then
    log_error "flock is required to prevent overlapping CodeRecall sessions."
    exit 1
fi
flock -n -E 75 9
LOCK_STATUS=$?
if [ "$LOCK_STATUS" -eq 75 ]; then
    log_error "A CodeRecall session is already running; skipping this invocation."
    exit 0
fi
if [ "$LOCK_STATUS" -ne 0 ]; then
    log_error "Could not acquire the CodeRecall session lock."
    exit "$LOCK_STATUS"
fi

# GUI environment - required for Cron to launch a terminal window
USER_ID=$(id -u)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_ID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

if ! USER_ENVIRONMENT=$(systemctl --user show-environment 2>> "$LOG_FILE"); then
    log_error "Could not read the user session environment. Is the graphical session running?"
    exit 1
fi

get_user_environment_value() {
    local requested_name=$1
    local name
    local value

    while IFS='=' read -r name value; do
        if [ "$name" = "$requested_name" ]; then
            printf '%s\n' "$value"
            return 0
        fi
    done <<< "$USER_ENVIRONMENT"

    return 1
}

DISPLAY="${DISPLAY:-$(get_user_environment_value DISPLAY)}"
WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-$(get_user_environment_value WAYLAND_DISPLAY)}"
XAUTHORITY="${XAUTHORITY:-$(get_user_environment_value XAUTHORITY)}"
export DISPLAY WAYLAND_DISPLAY XAUTHORITY

if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    log_error "No active graphical display was found in the user session environment."
    exit 1
fi

if [ -n "$XAUTHORITY" ] && [ ! -r "$XAUTHORITY" ]; then
    log_error "XAUTHORITY is not readable: $XAUTHORITY"
    exit 1
fi

if ! command -v gnome-terminal > /dev/null; then
    log_error "gnome-terminal is required when launching CodeRecall from Cron."
    exit 1
fi

gnome-terminal --wait --full-screen -- uv run main.py 2>> "$LOG_FILE"
exit $?
