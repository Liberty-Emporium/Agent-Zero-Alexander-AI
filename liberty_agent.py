#!/usr/bin/env python3
"""
Liberty Agent — Alexander AI Background Service
Runs silently on customer machines. Keeps a persistent connection
to the Alexander AI portal so Jay can monitor and assist anytime.

Customers never need to do anything — this starts automatically.
"""

import os
import sys
import json
import time
import uuid
import socket
import platform
import subprocess
import threading
import logging
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
PORTAL_URL    = os.getenv("LIBERTY_PORTAL_URL", "https://agent.install.alexanderai.site")
AGENT_TYPE    = os.getenv("LIBERTY_AGENT_TYPE", "agent-zero")   # hermes | agent-zero
CLIENT_ID     = os.getenv("LIBERTY_CLIENT_ID", "")          # Set at install time
INSTALL_TOKEN = os.getenv("LIBERTY_INSTALL_TOKEN", "")      # Set at install time
DASHBOARD_URL = os.getenv("LIBERTY_DASHBOARD_URL", "https://alexanderai.site")  # For auto-register
VERSION       = "1.0.0"
RECONNECT_DELAY = 15   # seconds between reconnect attempts
HEARTBEAT_INTERVAL = 30  # seconds between heartbeats

# ── Persistent machine ID ─────────────────────────────────────────────────────
def get_machine_id():
    """Generate or load a persistent unique ID for this machine."""
    id_paths = [
        Path.home() / ".liberty-agent" / "machine_id",
        Path("/tmp/.liberty_machine_id"),
    ]
    for p in id_paths:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists():
                mid = p.read_text().strip()
                if mid:
                    return mid
            mid = str(uuid.uuid4())
            p.write_text(mid)
            return mid
        except Exception:
            continue
    return str(uuid.uuid4())

# ── Machine info ──────────────────────────────────────────────────────────────
def get_machine_info():
    """Collect safe system info to show in Jay's dashboard."""
    info = {
        "machine_id":   get_machine_id(),
        "hostname":     socket.gethostname(),
        "os":           platform.system(),
        "os_release":   platform.release(),
        "os_version":   platform.version()[:80],
        "architecture": platform.machine(),
        "python":       platform.python_version(),
        "agent_type":   AGENT_TYPE,
        "agent_version": VERSION,
        "connected_at": datetime.utcnow().isoformat(),
    }

    # Disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        info["disk_total_gb"] = round(total / (1024**3), 1)
        info["disk_free_gb"]  = round(free  / (1024**3), 1)
    except Exception:
        pass

    # Hermes-specific info
    if AGENT_TYPE == "hermes":
        info.update(_hermes_info())

    # Agent Zero-specific info
    if AGENT_TYPE == "agent-zero":
        info.update(_agent_zero_info())

    return info

def _hermes_info():
    info = {}
    try:
        result = subprocess.run(["hermes", "--version"], capture_output=True, text=True, timeout=5)
        info["hermes_version"] = result.stdout.strip() or result.stderr.strip()
    except Exception:
        info["hermes_version"] = "unknown"
    hermes_path = Path.home() / ".hermes"
    info["hermes_path"] = str(hermes_path) if hermes_path.exists() else "not found"
    return info

def _agent_zero_info():
    info = {}
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=agent-zero", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=8
        )
        status = result.stdout.strip()
        info["docker_container"] = status if status else "not running"
    except Exception:
        info["docker_container"] = "docker not found"
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=5)
        info["docker_version"] = result.stdout.strip()
    except Exception:
        info["docker_version"] = "not installed"
    return info

# ── Allowed commands whitelist ─────────────────────────────────────────────────
ALLOWED_COMMANDS = [
    # System info
    "hostname", "whoami", "uname -a", "uname -r",
    "df -h", "free -h", "uptime", "date",
    # Process / service
    "ps aux", "top -bn1",
    # Hermes
    "hermes --version", "hermes status", "hermes logs",
    "ls ~/.hermes", "cat ~/.hermes/config.json",
    # Docker / Agent Zero
    "docker --version", "docker ps", "docker ps -a",
    "docker logs agent-zero", "docker logs alexander-ai",
    "docker inspect agent-zero",
    "docker stats --no-stream",
    # Network
    "curl -s http://localhost:50001/api/health",
    "curl -s http://localhost:8080/health",
    # Python
    "pip list", "python3 --version",
]

def is_allowed(cmd):
    cmd = cmd.strip()
    for allowed in ALLOWED_COMMANDS:
        if cmd == allowed or cmd.startswith(allowed):
            return True
    # Allow ls, cat on home dir files
    if cmd.startswith("ls ~/") or cmd.startswith("cat ~/"):
        return True
    return False

def run_command(cmd, timeout=30):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        return output[:8000], result.returncode, False
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Command took longer than {timeout}s", -1, True
    except Exception as e:
        return f"[ERROR] {e}", -1, False

# ── Socket.IO connection ───────────────────────────────────────────────────────
def run_agent():
    """Main agent loop — connect to portal and maintain connection."""
    try:
        import socketio
    except ImportError:
        print("[liberty-agent] Installing socketio...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "python-socketio[client]",
                        "websocket-client", "--quiet"])
        import socketio

    machine_id = get_machine_id()
    machine_info = get_machine_info()

    log(f"Starting Liberty Agent v{VERSION}")
    log(f"Machine ID: {machine_id}")
    log(f"Agent type: {AGENT_TYPE}")
    log(f"Portal: {PORTAL_URL}")

    # Auto-register machine_id with dashboard if client ID was provided at install
    if CLIENT_ID and INSTALL_TOKEN:
        try:
            import urllib.request as _ur, json as _json
            reg_data = _json.dumps({"machine_id": machine_id}).encode()
            req = _ur.Request(
                f"{DASHBOARD_URL}/api/clients/{CLIENT_ID}/link-machine",
                data=reg_data,
                headers={"Content-Type": "application/json",
                         "X-Install-Token": INSTALL_TOKEN}
            )
            _ur.urlopen(req, timeout=10)
            log(f"Machine registered with dashboard (client {CLIENT_ID})")
        except Exception as e:
            log(f"Auto-register skipped: {e}")

    while True:
        try:
            sio = socketio.Client(
                reconnection=False,   # we handle reconnect ourselves
                logger=False,
                engineio_logger=False,
            )

            @sio.on("connect")
            def on_connect():
                log("Connected to portal")
                sio.emit("machine_info", machine_info)

            @sio.on("disconnect")
            def on_disconnect():
                log("Disconnected from portal")

            @sio.on("echo_command")
            def on_echo_command(data):
                cmd    = data.get("cmd", "")
                cmd_id = data.get("cmd_id", "")
                log(f"Command received: {cmd[:60]}")
                if not is_allowed(cmd):
                    output = "[BLOCKED] Command not permitted."
                    rc = 1
                    timed_out = False
                else:
                    output, rc, timed_out = run_command(cmd)
                sio.emit("command_result", {
                    "type": "command_result",
                    "cmd": cmd,
                    "cmd_id": cmd_id,
                    "output": output,
                    "returncode": rc,
                    "timed_out": timed_out,
                })

            @sio.on("echo_message")
            def on_echo_message(data):
                # Silent — don't show anything to customer
                pass

            @sio.on("ping_agent")
            def on_ping(data):
                sio.emit("pong_agent", {
                    "machine_id": machine_id,
                    "ts": datetime.utcnow().isoformat(),
                })

            # Connect using machine_id as session
            connect_url = f"{PORTAL_URL}?session_id={machine_id}"
            sio.connect(connect_url, transports=["websocket"], wait=True,
                        wait_timeout=15)

            # Heartbeat loop
            while sio.connected:
                time.sleep(HEARTBEAT_INTERVAL)
                try:
                    # Refresh machine info on each heartbeat
                    fresh = get_machine_info()
                    sio.emit("machine_info", fresh)
                except Exception:
                    break

            sio.disconnect()

        except Exception as e:
            log(f"Connection error: {e} — retrying in {RECONNECT_DELAY}s")

        time.sleep(RECONNECT_DELAY)

# ── Logging (silent in production) ────────────────────────────────────────────
_VERBOSE = os.getenv("LIBERTY_VERBOSE", "0") == "1"

def log(msg):
    if _VERBOSE:
        print(f"[liberty-agent {datetime.utcnow().strftime('%H:%M:%S')}] {msg}", flush=True)

# ── Auto-start setup ───────────────────────────────────────────────────────────
def install_autostart():
    """Install the agent to auto-start on boot (cross-platform)."""
    script_path = Path(__file__).resolve()
    system = platform.system()

    if system == "Linux":
        _install_linux_autostart(script_path)
    elif system == "Darwin":
        _install_macos_autostart(script_path)
    elif system == "Windows":
        _install_windows_autostart(script_path)

def _install_linux_autostart(script_path):
    # Try systemd user service first, fall back to crontab
    service_dir = Path.home() / ".config" / "systemd" / "user"
    try:
        service_dir.mkdir(parents=True, exist_ok=True)
        service_content = f"""[Unit]
Description=Alexander AI Liberty Agent
After=network.target

[Service]
ExecStart={sys.executable} {script_path}
Restart=always
RestartSec=15
Environment=LIBERTY_AGENT_TYPE={AGENT_TYPE}
Environment=LIBERTY_PORTAL_URL={PORTAL_URL}

[Install]
WantedBy=default.target
"""
        svc_file = service_dir / "liberty-agent.service"
        svc_file.write_text(service_content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", "liberty-agent"], capture_output=True)
        subprocess.run(["systemctl", "--user", "start", "liberty-agent"], capture_output=True)
        log("Installed as systemd user service")
        return
    except Exception:
        pass

    # Fallback: crontab @reboot
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
        entry = f"@reboot LIBERTY_AGENT_TYPE={AGENT_TYPE} LIBERTY_PORTAL_URL={PORTAL_URL} {sys.executable} {script_path} &\n"
        if str(script_path) not in existing:
            new_cron = existing.rstrip() + "\n" + entry
            proc = subprocess.run(["crontab", "-"], input=new_cron, text=True, capture_output=True)
            log("Installed via crontab @reboot")
    except Exception:
        pass

def _install_macos_autostart(script_path):
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.alexanderai.liberty-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{script_path}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>LIBERTY_AGENT_TYPE</key>
        <string>{AGENT_TYPE}</string>
        <key>LIBERTY_PORTAL_URL</key>
        <string>{PORTAL_URL}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/liberty-agent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/liberty-agent.log</string>
</dict>
</plist>"""
    plist_file = plist_dir / "ai.alexanderai.liberty-agent.plist"
    plist_file.write_text(plist_content)
    subprocess.run(["launchctl", "load", str(plist_file)], capture_output=True)
    log("Installed as macOS LaunchAgent")

def _install_windows_autostart(script_path):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        cmd = f'"{sys.executable}" "{script_path}"'
        winreg.SetValueEx(key, "LibertyAgent", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        log("Installed in Windows registry Run key")
    except Exception as e:
        log(f"Windows autostart failed: {e}")

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--install" in sys.argv:
        install_autostart()
        print("[liberty-agent] Auto-start installed. Agent will run on every boot.")
        sys.exit(0)

    if "--setup" in sys.argv:
        # Called by installer — install autostart then run
        install_autostart()

    # Run the agent
    run_agent()
