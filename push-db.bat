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

REM trakttv.db is over GitHub's 100 MB blob limit — must use Git LFS.
git lfs install >nul 2>&1
if not exist ".gitattributes" (
  git lfs track "trakttv.db"
  git add .gitattributes
)

git add trakttv.db
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "DB update"
  git push
) else (
  echo No DB changes to push.
)
