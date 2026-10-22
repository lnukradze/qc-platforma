@echo off
rem NAPR QC platform - one-time setup (Python env + libraries + local data).
rem ASCII only: cmd.exe misreads UTF-8 batch files. Georgian messages come from Python.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto deps

where uv >nul 2>nul
if not errorlevel 1 (
  echo Creating .venv with uv ...
  uv venv .venv --python ">=3.12" --system-certs
  if errorlevel 1 goto fail
  goto deps
)
where py >nul 2>nul
if not errorlevel 1 (
  echo Creating .venv with py -3 ...
  py -3 -m venv .venv
  if errorlevel 1 goto fail
  goto deps
)
echo [!] Python not found. Install uv:  winget install astral-sh.uv   or Python 3.12+
goto fail

:deps
echo Installing libraries ...
where uv >nul 2>nul
if not errorlevel 1 (
  uv pip install --python ".venv\Scripts\python.exe" --system-certs -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 goto fail

".venv\Scripts\python.exe" scripts\setup_data.py
if errorlevel 1 goto fail
pause
exit /b 0

:fail
echo.
echo [!] Setup stopped - see the error above.
pause
exit /b 1
