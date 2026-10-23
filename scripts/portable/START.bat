@echo off
rem NAPR QC platform - portable version: http://127.0.0.1:8200 (built-in Python, no installation).
rem ASCII only: cmd.exe misreads UTF-8 batch files. Georgian messages come from Python.
cd /d "%~dp0"
if not exist "runtime\python.exe" (
  echo [!] runtime\python.exe not found - extract the whole ZIP first, then run START.bat again.
  pause
  exit /b 1
)
"runtime\python.exe" run_portable.py %*
pause
