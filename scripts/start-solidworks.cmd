@echo off
setlocal EnableExtensions
rem Works from PowerShell when .ps1 scripts are blocked by execution policy.
rem This does not install an add-in. It attaches to the SOLIDWORKS window
rem you already opened and listens until you close this window.
set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul
set "REPO_ROOT=%CD%"
popd

set "LISTENER=%REPO_ROOT%\solidworks-mcp\scripts\start_listener.py"
if not exist "%LISTENER%" (
  echo Missing %LISTENER% — run this from a Plygon-mcp checkout, not a Cursor cache folder.
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
echo Starting Plygon SOLIDWORKS listener from %REPO_ROOT%
echo Open the SOLIDWORKS window first. Leave this window open. Ctrl-C stops the listener.
"%UV%" run --directory "%REPO_ROOT%\solidworks-mcp" --with pywin32 python "%LISTENER%" %*
exit /b %ERRORLEVEL%
