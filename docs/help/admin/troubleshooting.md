# Troubleshooting

| Symptom | Check |
|---------|--------|
| Login button errors | `TRAKT_CLIENT_ID/SECRET`, redirect URI exact match |
| Empty latest lists | API credentials; click Refresh; check `logs/app.log` |
| My Movies/Shows missing titles that are on Trakt | Reload My Movies (full watchlist/watched sync). App used to fetch only the first Trakt page (~10); it now paginates. |
| No streaming providers | `TMDB_API_KEY` set? title has `tmdb_id`? |
| Not admin after login | `ADMIN_TRAKT_USERNAMES` matches Trakt username; bootstrap not already locked to someone else |
| Cookie/session issues on HTTP | use HTTPS `run.py`, or `run.py --http` with `SESSION_COOKIE_SECURE=0` |
