$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw "Backend environment missing. Create it and install backend\requirements.txt as shown in README.md."
}
Set-Location $Root
& $Python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
