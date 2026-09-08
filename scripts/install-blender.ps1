#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $RepoRoot "blender-mcp\scripts\install_addon.py"
if (-not (Test-Path $Installer)) {
    Write-Error "Missing $Installer — run this from a Plygon-mcp checkout."
}
Write-Host "Installing Plygon Blender MCP from $RepoRoot"
& python $Installer @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
