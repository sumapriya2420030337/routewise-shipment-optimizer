$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw "Backend environment missing. Create it and install backend\requirements.txt as shown in README.md."
}

Set-Location $Root
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $Root 'frontend')
npm test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run lint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run build
exit $LASTEXITCODE
