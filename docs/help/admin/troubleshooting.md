# Troubleshooting

| Symptom | Check |
|---------|--------|
| Login button errors | `TRAKT_CLIENT_ID/SECRET`, redirect URI exact match |
| Empty latest lists | API credentials; click Refresh; check `logs/app.log` |
| Too many Trakt calls / 429s | Open **Admin → Trakt cache log**. `hit` = local, `probe` = 1 last_activities, `fetch` + `calls=` = Trakt HTTP. Scheduler jobs use `reason=scheduler` / `alerts` / `job`. 429s show as errors. |
| My Movies/Shows missing titles that are on Trakt | Click **Refresh from Trakt**, or wait for the admin Trakt read-cache TTL (default 2 hours). In-app writes update local cache immediately; trakt.tv-only adds wait for that window. |
| No streaming providers | `TMDB_API_KEY` set? title has `tmdb_id`? |
| Not admin after login | `ADMIN_TRAKT_USERNAMES` matches Trakt username; bootstrap not already locked to someone else |
| Cookie/session issues on HTTP | use HTTPS `run.py`, or `run.py --http` with `SESSION_COOKIE_SECURE=0` |
| Progress panel 429 / “rate-limiting” | Wait ~1 minute and **Retry**. Check `logs/app.log` for a burst of `/seasons (429)` during list sync — that should stop after the first 429 |
