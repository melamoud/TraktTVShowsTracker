# Troubleshooting

| Symptom | Check |
|---------|--------|
| Login button errors | `TRAKT_CLIENT_ID/SECRET`, redirect URI exact match |
| Empty latest lists | API credentials; click Refresh; check `logs/app.log` |
| My Movies/Shows missing titles that are on Trakt | Open My movies/shows (auto-sync via `last_activities`) or click **Refresh from Trakt**. Title search backfills missing local metadata; in-app writes no longer stamp unrelated watchlist activity as already synced. |
| No streaming providers | `TMDB_API_KEY` set? title has `tmdb_id`? |
| Not admin after login | `ADMIN_TRAKT_USERNAMES` matches Trakt username; bootstrap not already locked to someone else |
| Cookie/session issues on HTTP | use HTTPS `run.py`, or `run.py --http` with `SESSION_COOKIE_SECURE=0` |
| Progress panel 429 / “rate-limiting” | Wait ~1 minute and **Retry**. Check `logs/app.log` for a burst of `/seasons (429)` during list sync — that should stop after the first 429 |
