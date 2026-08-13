# System configuration

## Scheduler

The scheduler controls two background jobs:

- **Catalog sync** — refreshes newest Trakt `/movies` and `/shows` updates and enriches metadata for the Latest pages.
- **Media alerts** — checks release day, new streaming providers, and newly aired episodes/seasons for all users (Trakt calendar + TMDB). Moderately network-heavy, so the default is clock-aligned every **4 hours**.

Admins can change the schedule from **Admin → Scheduler** without restarting the server. Each job can run either:

- **Interval** — catalog: every *N* minutes; alerts: every *N* hours **at :00** in the chosen timezone (e.g. every 4 in `America/New_York` → 12am / 4am / 8am / 12pm / 4pm / 8pm)
- **Daily at a specific time** — e.g. `08:00`

Jobs can also be enabled or disabled individually. The page shows the next scheduled run time. **Run alert check now** is available from Admin, Scheduler, and (for admins) the Alerts page. There is no automatic run a few minutes after restart — the next clock slot (or a manual run) is used.

Each cache object decision is written to `logs/app.log` as `Cache user_media hit|probe|fetch user=… calls=… source=…`. Watch it live from **Admin → Trakt cache log**. Successful Trakt HTTP calls are not logged (too noisy); 429s still appear as warnings.

## Trakt read cache

**Admin → Scheduler** also has **Trakt read cache TTL (hours)** (default `2`). Page loads — including browser Back — read SQLite for that user’s watchlist, lists, calendar, per-show progress, and recommendations. Trakt is contacted when **that object** is older than the TTL, after **Refresh from Trakt**, or when an in-app write could not update the local object. Progress, My, Latest tags, Recs tags, and Alerts share the same title/progress rows, so a watch on Progress is what Alerts sees. Changes made only on trakt.tv wait for the TTL or a manual refresh.

## Environment variables

Most settings are now editable in the UI, but defaults are still read from `.env` on the first app start:

- `CATALOG_SYNC_INTERVAL_MINUTES` — default catalog sync interval (default `60`)
- `ALERTS_INTERVAL_HOURS` — default media alerts clock interval (default `4`)
- `ALERTS_TIMEZONE` — IANA timezone for alert clock (default `America/New_York`)
- `ALERTS_STARTUP_DELAY_SECONDS` — unused for scheduling (kept for compatibility; default `0`)
- `TRAKT_READ_CACHE_HOURS` — default Trakt read-cache TTL on first scheduler-config row (default `2`)
- `PROVIDER_SYNC_INTERVAL_HOURS` — legacy fallback only

After the first start, the database copy of the scheduler settings is the source of truth. Restarting the server without changing `.env` keeps the last saved UI settings.

## Other important `.env` keys

- `TRAKT_CLIENT_ID` / `TRAKT_CLIENT_SECRET` / `TRAKT_REDIRECT_URI`
- `TMDB_API_KEY` / `STREAMING_REGION=US`
- `ADMIN_TRAKT_USERNAMES` — first matching login becomes admin
- `ADMIN_ALLOW_ENV_PROMOTE=0` — keep at 0 so nobody else becomes admin just by editing env later
- `PORT=8300`, `PUBLIC_HOST=tvtracker.melamoud.com`

See `docs/SETUP.md` and `config.py`.
