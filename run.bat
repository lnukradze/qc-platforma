@echo off
rem NAPR QC platform (prototype) - local run: http://127.0.0.1:8200
rem ASCII only: cmd.exe misreads UTF-8 batch files. Georgian messages come from Python.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [!] .venv not found - run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run_local.py
pause
