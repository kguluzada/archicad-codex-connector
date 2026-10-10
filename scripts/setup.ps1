# Run from a copied connector checkout on the Windows machine running Archicad.
[CmdletBinding()]
param([ValidateSet('3.12', '3.13', '3.14')][string]$PythonVersion = '3.12')
$ErrorActionPreference = 'Stop'
$ConnectorRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ConnectorRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'Install uv from https://docs.astral.sh/uv/getting-started/installation/ then rerun.'
    }
    & uv sync --frozen --no-dev --python $PythonVersion
    if ($LASTEXITCODE -ne 0) { throw 'Locked Python installation failed.' }
    $ConnectorExe = Join-Path $ConnectorRoot '.venv\Scripts\archicad-connector.exe'
    & $ConnectorExe --version
    if ($LASTEXITCODE -ne 0) { throw 'Connector entrypoint failed.' }
    Write-Host "Installed. Start licensed Archicad, install matching Tapir 1.7.0 and save a test project."
    Write-Host "Read-only diagnostic: & '$ConnectorExe' diagnose"
    Write-Host "Codex: codex mcp add archicad -- `"$ConnectorExe`" --ports 19723-19743 serve"
} finally {
    Pop-Location
}
