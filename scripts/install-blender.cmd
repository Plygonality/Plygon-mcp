@echo off
setlocal EnableExtensions
rem Works from PowerShell when .ps1 scripts are blocked by execution policy.
set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul
set "REPO_ROOT=%CD%"
popd

set "INSTALLER=%REPO_ROOT%\blender-mcp\scripts\install_addon.py"
if not exist "%INSTALLER%" (
  echo Missing %INSTALLER% — run this from a Plygon-mcp checkout.
  exit /b 1
)

set "UV=%USERPROFILE%\.local\bin\uv.exe"
if exist "%UV%" goto run
where uv >nul 2>&1
if errorlevel 1 (
  echo uv.exe was not found. Install uv first:
  echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  echo If that says uv.exe is in use, quit Cursor from the tray, or skip if this already works:
  echo   "%USERPROFILE%\.local\bin\uvx.exe" --version
  exit /b 1
)
for /f "delims=" %%I in ('where uv') do (
  set "UV=%%I"
  goto run
)

:run
echo Installing Plygon Blender MCP from %REPO_ROOT%
"%UV%" run --no-project python "%INSTALLER%" %*
exit /b %ERRORLEVEL%
