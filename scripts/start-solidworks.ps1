#Requires -Version 5.1
$ErrorActionPreference = "Stop"
# If PowerShell refuses to load this file ("running scripts is disabled"),
# run scripts\start-solidworks.cmd instead — cmd.exe is not blocked.
# This does not install an add-in. Open SOLIDWORKS first, then leave this window open.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Listener = Join-Path $RepoRoot "solidworks-mcp\scripts\start_listener.py"
if (-not (Test-Path $Listener)) {
    Write-Error "Missing $Listener — run this from a Plygon-mcp checkout, not a Cursor cache folder."
}
Write-Host "Starting Plygon SOLIDWORKS listener from $RepoRoot"
Write-Host "Open the SOLIDWORKS window first. Leave this window open. Ctrl-C stops the listener."
$UvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($UvCommand) {
    $Uv = $UvCommand.Source
} else {
    $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
}
if (-not (Test-Path $Uv)) {
    Write-Error "uv.exe was not found. Install uv first: powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`""
}
& $Uv run --directory (Join-Path $RepoRoot "solidworks-mcp") --with pywin32 python $Listener @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
