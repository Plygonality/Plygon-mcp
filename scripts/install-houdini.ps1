#Requires -Version 5.1
$ErrorActionPreference = "Stop"
# Resolve the repo even if you run this from C:\Users\you (do not cd first).
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $RepoRoot "houdini-mcp\scripts\install_package.py"
if (-not (Test-Path $Installer)) {
    Write-Error "Missing $Installer — run this from a Plygon-mcp checkout, not a Cursor cache folder named houdini-mcp."
}
Write-Host "Installing Plygon Houdini MCP from $RepoRoot"
& python $Installer @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
