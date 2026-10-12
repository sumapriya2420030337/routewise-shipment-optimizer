$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root 'frontend'
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    throw "Frontend dependencies missing. Run npm ci in frontend\ as shown in README.md."
}
Set-Location $Frontend
npm run dev -- --host 127.0.0.1
exit $LASTEXITCODE
