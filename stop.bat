@echo off
setlocal
cd /d "%~dp0"

echo Stopping TraktTV Shows Tracker on port 8300...

if exist ".server.pid" (
  set /p PID=<.server.pid
  echo Stopping PID from .server.pid: %PID%
  taskkill /PID %PID% /F >nul 2>&1
  del /f /q .server.pid >nul 2>&1
)

REM Also kill anything still listening on 8300 (stale processes break new routes).
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8300" ^| findstr "LISTENING"') do (
  echo Stopping listener PID %%P
  taskkill /PID %%P /F >nul 2>&1
)

echo Done.
