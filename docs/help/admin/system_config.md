# System configuration

## Scheduler

The scheduler controls two background jobs:

- **Catalog sync** — refreshes newest Trakt `/movies` and `/shows` updates and enriches metadata for the Latest pages.
- **Media alerts** — checks release day, new streaming providers, and newly aired episodes/seasons for all users.

Admins can change the schedule from **Admin → Scheduler** without restarting the server. Each job can run either:

- **Interval** — every *N* minutes/hours
- **Daily at a specific time** — e.g. `08:00` and `20:00`

Jobs can also be enabled or disabled individually. The page shows the next scheduled run time and a **Run alert check now** button for manual execution.

The very first interval-based media alerts run after boot is delayed by **Startup delay** (default 120 seconds). This delay does not apply to cron schedules or to changes made through the admin UI.

## Environment variables

Most settings are now editable in the UI, but defaults are still read from `.env` on the first app start:

- `CATALOG_SYNC_INTERVAL_MINUTES` — default catalog sync interval (default `60`)
- `ALERTS_INTERVAL_HOURS` — default media alerts interval (default `6`)
- `ALERTS_STARTUP_DELAY_SECONDS` — delay before first media alerts run at boot (default `120`)
- `PROVIDER_SYNC_INTERVAL_HOURS` — legacy fallback only

After the first start, the database copy of the scheduler settings is the source of truth. Restarting the server without changing `.env` keeps the last saved UI settings.

## Other important `.env` keys

- `TRAKT_CLIENT_ID` / `TRAKT_CLIENT_SECRET` / `TRAKT_REDIRECT_URI`
- `TMDB_API_KEY` / `STREAMING_REGION=US`
- `ADMIN_TRAKT_USERNAMES` — first matching login becomes admin
- `ADMIN_ALLOW_ENV_PROMOTE=0` — keep at 0 so nobody else becomes admin just by editing env later
- `PORT=8300`, `PUBLIC_HOST=tvtracker.melamoud.com`

See `docs/SETUP.md` and `config.py`.
