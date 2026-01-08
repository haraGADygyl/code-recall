#!/bin/bash

# Configuration
# Automatically detect the project directory relative to this script
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# Load environment variables if .env exists
if [ -f .env ]; then
    # We use a simple grep/cut approach to avoid sourcing issues
    EXTRA_PATH=$(grep EXTRA_PATH .env | cut -d'=' -f2 | tr -d '"')
fi

# Set up PATH - includes user local bin and any extra paths from .env
export PATH="${EXTRA_PATH:+$EXTRA_PATH:}$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# GUI Environment - required for Cron to launch a terminal window
# You can override these in your .env if they differ
USER_ID=$(id -u)
export DISPLAY=${DISPLAY:-:1}
export XAUTHORITY=${XAUTHORITY:-/run/user/$USER_ID/gdm/Xauthority}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$USER_ID/bus}

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
