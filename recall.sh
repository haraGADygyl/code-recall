#!/bin/bash

# Configuration
# Automatically detect the project directory relative to this script
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# Load the optional extra PATH if .env exists
if [ -f .env ]; then
    # Avoid sourcing .env because it may contain values that are not shell-safe.
    EXTRA_PATH=$(grep -m1 '^EXTRA_PATH=' .env | cut -d'=' -f2- | tr -d '"')
fi

# Set up PATH - includes user local bin and any extra paths from .env
export PATH="${EXTRA_PATH:+$EXTRA_PATH:}$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# GUI environment - required for Cron to launch a terminal window
USER_ID=$(id -u)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_ID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

log_error() {
    printf '%s ERROR: %s\n' "$(date --iso-8601=seconds)" "$1" >> "$PROJECT_DIR/recall_error.log"
}

if ! USER_ENVIRONMENT=$(systemctl --user show-environment 2>> "$PROJECT_DIR/recall_error.log"); then
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

# Run the app in a new terminal window
# We redirect errors to a log file in case cron fails to launch the terminal
{
    if command -v gnome-terminal > /dev/null; then
        gnome-terminal --wait --full-screen -- uv run main.py
    else
        uv run main.py
    fi
} 2>> recall_error.log

# VRAM Optimization: stop the model after the app exits to free up GPU memory
# Try to get MODEL_NAME from .env, fallback to gemma2:2b
MODEL_NAME=$(grep MODEL_NAME .env | cut -d'=' -f2 | tr -d '"' || echo "gemma2:2b")
ollama stop "$MODEL_NAME"
