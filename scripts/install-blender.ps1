#Requires -Version 5.1
$ErrorActionPreference = "Stop"
# If PowerShell refuses to load this file ("running scripts is disabled"),
# run scripts\install-blender.cmd instead — cmd.exe is not blocked.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $RepoRoot "blender-mcp\scripts\install_addon.py"
if (-not (Test-Path $Installer)) {
    Write-Error "Missing $Installer — run this from a Plygon-mcp checkout."
}
Write-Host "Installing Plygon Blender MCP from $RepoRoot"
$UvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($UvCommand) {
    $Uv = $UvCommand.Source
} else {
    $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
}
if (-not (Test-Path $Uv)) {
    Write-Error "uv.exe was not found. Install uv first: powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`""
}
& $Uv run --no-project python $Installer @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
