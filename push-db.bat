@echo off
setlocal
cd /d "%~dp0instance"

if not exist ".git" (
  echo instance\ is not a git repo yet. Create the private GitHub repo
  echo melamoud/TraktTVShowsTracker-db, then ask the agent to finish the first push.
  exit /b 1
)

if not exist "trakttv.db" (
  echo No instance\trakttv.db to back up.
  exit /b 1
)

git add trakttv.db
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "DB update"
  git push
) else (
  echo No DB changes to push.
)
