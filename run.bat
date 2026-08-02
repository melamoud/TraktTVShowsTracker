@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtualenv...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\pip.exe install -r requirements.txt
)

if not exist "cert.pem" (
  echo Generating self-signed TLS certificate...
  .venv\Scripts\python.exe generate_cert.py
)

if not exist ".env" (
  echo WARNING: .env missing. Copy .env.example to .env and fill Trakt/TMDB keys.
)

echo Starting TraktTV Shows Tracker...
.venv\Scripts\python.exe run.py %*
