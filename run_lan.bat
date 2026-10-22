@echo off
rem NAPR QC platform - demo on the local network (phone/tablet on the same Wi-Fi).
rem A new demo PIN is printed on every start. Use only for a short, closed demo.
rem ASCII only: cmd.exe misreads UTF-8 batch files. Georgian messages come from Python.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [!] .venv not found - run setup.bat first.
  pause
  exit /b 1
)
if not exist "data\platform.db" ".venv\Scripts\python.exe" scripts\build_db.py
".venv\Scripts\python.exe" scripts\serve_lan.py
pause
