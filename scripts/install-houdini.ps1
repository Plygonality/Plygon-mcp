#Requires -Version 5.1
$ErrorActionPreference = "Stop"
# Resolve the repo even if you run this from C:\Users\you (do not cd first).
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $RepoRoot "houdini-mcp\scripts\install_package.py"
if (-not (Test-Path $Installer)) {
    Write-Error "Missing $Installer — run this from a Plygon-mcp checkout, not a Cursor cache folder named houdini-mcp."
}
Write-Host "Installing Plygon Houdini MCP from $RepoRoot"
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
