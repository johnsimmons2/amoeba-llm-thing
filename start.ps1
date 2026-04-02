# Start the AI Sandbox (Windows)
# Prerequisites: Python 3.12+, Node.js 20+, Ollama running locally

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  AI SANDBOX" -ForegroundColor Cyan
Write-Host "  ----------" -ForegroundColor DarkGray
Write-Host ""

# Validate prerequisites
foreach ($cmd in @("python", "node")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "Required command not found: $cmd"
        exit 1
    }
}

# Install Python dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
pip install -r "$Root\requirements.txt" --quiet

# Install dashboard dependencies
Write-Host "Installing dashboard dependencies..." -ForegroundColor Yellow
Push-Location "$Root\dashboard"
npm install --silent
Pop-Location

# Launch via launcher.py (copies project to runs/<id>, handles restarts)
Write-Host "Launching sandbox..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Dashboard  -> http://localhost:5173" -ForegroundColor Cyan
Write-Host "  API server -> http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Make sure Ollama is running: ollama serve" -ForegroundColor Yellow
Write-Host "  Pull the default model first: ollama pull llama3.2" -ForegroundColor Yellow
Write-Host ""

Set-Location $Root
python launcher.py --dashboard
