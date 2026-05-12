#!/usr/bin/env bash
# Agent Zero — Alexander AI Installer (Linux/Mac)
# Wraps the official Agent Zero installer, then adds:
#   1. OpenRouter API key setup
#   2. Liberty Agent (Alexander AI remote support dashboard)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Liberty-Emporium/Agent-Zero-Alexander-AI/main/scripts/install-alexander-ai.sh | bash

set -euo pipefail

cyan()   { printf "\033[36m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
bold()   { printf "\033[1m%s\033[0m\n" "$*"; }

bold ""
bold "╭─────────────────────────────────────────────╮"
bold "│   AGENT ZERO — Alexander AI Edition         │"
bold "│   Installer for Linux / macOS               │"
bold "╰─────────────────────────────────────────────╯"
bold ""

# ── Step 1: Run official Agent Zero installer ─────────────────────────────
cyan "→ Running official Agent Zero installer…"
curl -fsSL https://bash.agent-zero.ai | bash
green "  Agent Zero installed ✓"

# ── Step 2: OpenRouter API key ────────────────────────────────────────────
cyan "→ Setting up OpenRouter API key…"
A0_ENV="$HOME/agent-zero/.env"
# Also check common Docker volume location
if [[ ! -f "$A0_ENV" ]]; then
  A0_ENV="$HOME/.agent-zero/.env"
fi

if [[ -f "$A0_ENV" ]] && grep -qE "^OPENROUTER_API_KEY=sk-or" "$A0_ENV" 2>/dev/null; then
  green "  OpenRouter API key already set ✓"
else
  echo ""
  yellow "  OpenRouter gives you access to 100+ AI models (free tier available)."
  yellow "  Get your key at: https://openrouter.ai/keys"
  echo ""
  printf "  Paste your OpenRouter API key (or press Enter to skip): "
  read -r OR_KEY
  if [[ -n "$OR_KEY" ]]; then
    mkdir -p "$(dirname "$A0_ENV")"
    # Remove existing key if present, then append
    if [[ -f "$A0_ENV" ]]; then
      sed -i '/^OPENROUTER_API_KEY=/d' "$A0_ENV" 2>/dev/null || true
    fi
    echo "OPENROUTER_API_KEY=$OR_KEY" >> "$A0_ENV"
    green "  OpenRouter API key saved ✓"
  else
    yellow "  Skipped — add it later in Agent Zero Settings → API Keys"
  fi
fi

# ── Step 3: Liberty Agent ─────────────────────────────────────────────────
cyan "→ Installing Liberty Agent (Alexander AI remote support)…"
LIBERTY_SCRIPT="$HOME/liberty_agent.py"
LIBERTY_URL="https://raw.githubusercontent.com/Liberty-Emporium/Agent-Zero-Alexander-AI/main/liberty_agent.py"

curl -fsSL "$LIBERTY_URL" -o "$LIBERTY_SCRIPT"
chmod +x "$LIBERTY_SCRIPT"
green "  Liberty Agent downloaded ✓"

# Install Python deps
python3 -m pip install "python-socketio[client]" websocket-client --quiet --break-system-packages 2>/dev/null || \
  python3 -m pip install "python-socketio[client]" websocket-client --quiet 2>/dev/null || true
green "  Python deps installed ✓"

# Install as systemd user service (Linux)
if command -v systemctl &>/dev/null; then
  SVC_DIR="$HOME/.config/systemd/user"
  mkdir -p "$SVC_DIR"
  cat > "$SVC_DIR/liberty-agent.service" <<SYSTEMD_EOF
[Unit]
Description=Liberty Agent — Alexander AI Remote Support
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$(which python3) $LIBERTY_SCRIPT
Restart=always
RestartSec=15
Environment=LIBERTY_AGENT_TYPE=agent-zero
Environment=LIBERTY_PORTAL_URL=https://agent.install.alexanderai.site

[Install]
WantedBy=default.target
SYSTEMD_EOF
  systemctl --user daemon-reload 2>/dev/null && \
  systemctl --user enable liberty-agent 2>/dev/null && \
  systemctl --user restart liberty-agent 2>/dev/null && \
  green "  Liberty Agent service enabled + started ✓" || true
fi

# macOS launchd
if [[ "$(uname)" == "Darwin" ]]; then
  PLIST_DIR="$HOME/Library/LaunchAgents"
  mkdir -p "$PLIST_DIR"
  cat > "$PLIST_DIR/ai.alexanderai.liberty-agent.plist" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.alexanderai.liberty-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which python3)</string>
        <string>$LIBERTY_SCRIPT</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>LIBERTY_AGENT_TYPE</key>
        <string>agent-zero</string>
        <key>LIBERTY_PORTAL_URL</key>
        <string>https://agent.install.alexanderai.site</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLIST_EOF
  launchctl load "$PLIST_DIR/ai.alexanderai.liberty-agent.plist" 2>/dev/null && \
    green "  Liberty Agent LaunchAgent loaded ✓" || true
fi

# Always ensure running right now
if ! pgrep -f liberty_agent.py >/dev/null 2>&1; then
  mkdir -p "$HOME/.liberty-agent"
  nohup python3 "$LIBERTY_SCRIPT" >> "$HOME/.liberty-agent/agent.log" 2>&1 &
  green "  Liberty Agent running in background (PID: $!) ✓"
else
  green "  Liberty Agent already running ✓"
fi

# ── Done ──────────────────────────────────────────────────────────────────
bold ""
bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
green "  Install complete!"
bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Agent Zero is ready. Start it with:"
echo "    docker run -p 50080:80 -v ./agent-zero:/a0 agent0ai/agent-zero"
echo "  Then open: http://localhost:50080"
echo ""
echo "  Liberty Agent is running — your machine is visible"
echo "  in Jay's support dashboard. 🟢"
echo ""
cyan "Happy building. 🚀"
