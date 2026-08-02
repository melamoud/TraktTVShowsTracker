# Release alerts

Use **Alert when streaming** on a title (Latest or detail) when you want a heads-up once it appears on streaming.

## How it works

1. You click **Alert when streaming** — a local watch row is stored  
2. A background job (about every `PROVIDER_SYNC_INTERVAL_HOURS`, default 12h) checks TMDB providers  
3. When the title appears on **any** subscription-style offer (flatrate / ads / free), you get an **in-app** notification under **Alerts**  
4. That alert fires even if you do not subscribe to the service  

## Requirements

- Free `TMDB_API_KEY` in `.env` (without it, the checker cannot see providers)  
- Server started with the scheduler (normal `run.bat` / `run.py`, not `--no-scheduler`)  

Admins can also trigger **Run release check now** from the Admin dashboard.
