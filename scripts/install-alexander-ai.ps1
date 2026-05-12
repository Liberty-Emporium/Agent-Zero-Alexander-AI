# Agent Zero — Alexander AI Installer (Windows)
# Run in PowerShell: irm https://raw.githubusercontent.com/Liberty-Emporium/Agent-Zero-Alexander-AI/main/scripts/install-alexander-ai.ps1 | iex

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n  --> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }

Clear-Host
Write-Host ""
Write-Host "  ===========================================" -ForegroundColor Magenta
Write-Host "   AGENT ZERO - Alexander AI Edition" -ForegroundColor White
Write-Host "   Windows Installer" -ForegroundColor DarkCyan
Write-Host "  ===========================================" -ForegroundColor Magenta
Write-Host ""

# ── Step 1: Official Agent Zero installer ────────────────────────────────
Write-Step "Running official Agent Zero installer..."
irm https://ps.agent-zero.ai | iex
Write-OK "Agent Zero installed"

# ── Step 2: OpenRouter API key ────────────────────────────────────────────
Write-Step "Setting up OpenRouter API key..."
$a0EnvPath = "$env:USERPROFILE\agent-zero\.env"
$orAlreadySet = $false
if (Test-Path $a0EnvPath) {
    $envContent = Get-Content $a0EnvPath -Raw
    if ($envContent -match "OPENROUTER_API_KEY=sk-or") {
        $orAlreadySet = $true
        Write-OK "OpenRouter API key already set"
    }
}

if (-not $orAlreadySet) {
    Write-Host ""
    Write-Warn "OpenRouter gives you access to 100+ AI models (free tier available)."
    Write-Warn "Get your key at: https://openrouter.ai/keys"
    Write-Host ""
    $orKey = Read-Host "  Paste your OpenRouter API key (or press Enter to skip)"
    if ($orKey -ne "") {
        if (-not (Test-Path (Split-Path $a0EnvPath))) {
            New-Item -ItemType Directory -Path (Split-Path $a0EnvPath) -Force | Out-Null
        }
        if (Test-Path $a0EnvPath) {
            $lines = Get-Content $a0EnvPath | Where-Object { $_ -notmatch "^OPENROUTER_API_KEY=" }
            $lines + "OPENROUTER_API_KEY=$orKey" | Set-Content $a0EnvPath
        } else {
            "OPENROUTER_API_KEY=$orKey" | Set-Content $a0EnvPath
        }
        Write-OK "OpenRouter API key saved"
    } else {
        Write-Warn "Skipped — add it later in Agent Zero Settings -> API Keys"
    }
}

# ── Step 3: Liberty Agent ─────────────────────────────────────────────────
Write-Step "Installing Liberty Agent (Alexander AI remote support)..."

$libertyScript = "$env:USERPROFILE\liberty_agent.py"
$libertyUrl = "https://raw.githubusercontent.com/Liberty-Emporium/Agent-Zero-Alexander-AI/main/liberty_agent.py"

Invoke-WebRequest -Uri $libertyUrl -OutFile $libertyScript -UseBasicParsing
Write-OK "Liberty Agent downloaded"

# Install Python deps
Write-Step "Installing Python dependencies..."
pip install "python-socketio[client]" websocket-client --quiet 2>$null
Write-OK "Python deps installed"

# Create Task Scheduler entry for auto-start on boot
Write-Step "Registering Liberty Agent as a startup task..."
$taskName = "LibertyAgent-AlexanderAI"
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $pythonPath) { $pythonPath = "python" }

$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $libertyScript
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$env_vars = @{
    "LIBERTY_AGENT_TYPE" = "agent-zero"
    "LIBERTY_PORTAL_URL" = "https://agent.install.alexanderai.site"
}

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null
    Write-OK "Liberty Agent scheduled task registered (runs at login)"
} catch {
    Write-Warn "Could not register scheduled task — starting manually instead"
}

# Start it right now in background
Write-Step "Starting Liberty Agent..."
$logDir = "$env:USERPROFILE\.liberty-agent"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$proc = Start-Process -FilePath $pythonPath -ArgumentList $libertyScript `
    -RedirectStandardOutput "$logDir\agent.log" `
    -RedirectStandardError "$logDir\agent-err.log" `
    -WindowStyle Hidden -PassThru
Write-OK "Liberty Agent running in background (PID: $($proc.Id))"

# ── Done ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ===========================================" -ForegroundColor Green
Write-Host "   INSTALL COMPLETE!" -ForegroundColor White
Write-Host "  ===========================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Start Agent Zero:" -ForegroundColor White
Write-Host "   docker run -p 50080:80 -v ./agent-zero:/a0 agent0ai/agent-zero" -ForegroundColor Cyan
Write-Host "   Then open: http://localhost:50080" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Liberty Agent is running — your machine is" -ForegroundColor White
Write-Host "   visible in Jay's support dashboard. " -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to close"
