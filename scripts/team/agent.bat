@echo off
rem Start a team AI agent:  agent.bat ^<lead^|backend^|ui^|qa^> [claude-account-name]
rem ASCII only: cmd.exe misreads UTF-8 batch files. Details: docs\team\README.md
if "%~1"=="" (
  echo Usage: agent.bat lead ^| backend salome-1 ^| ui salome-2 ^| qa
  pause
  exit /b 1
)
if "%~2"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agent.ps1" -Role %1
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agent.ps1" -Role %1 -Account %2
)
if errorlevel 1 pause
