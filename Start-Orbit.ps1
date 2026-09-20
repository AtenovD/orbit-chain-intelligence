$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Building Orbit frontend..."
Push-Location (Join-Path $projectRoot "frontend")
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

Write-Host "Preparing database..."
Push-Location $projectRoot
try {
    python -m pip install -e ".[dev]"
    python .\scripts\bootstrap_db.py
    Write-Host "Orbit: http://127.0.0.1:8000"
    Write-Host "API docs: http://127.0.0.1:8000/docs"
    python -m uvicorn orchestrator.main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
