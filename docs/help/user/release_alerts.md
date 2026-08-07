# Alerts

In-app messages under **Alerts** in the nav (badge = unread). They cover titles on your **Wishlist** and **personal lists**.

This is separate from **Streaming vs Found on** (where a title plays / where you found it).

## What you can get

| Alert | Meaning |
|-------|---------|
| **Movie release date** | A listed movie’s release day arrives |
| **Added to a streaming service** | Any service starts carrying that title (one alert per new service) |
| **New episode or season** | An episode aired; if a full season drops the same day, one season alert instead. A show premiere is announced by its S01E01 episode alert — there is no separate show “release” alert |
| **New user signed up** | Admins only — first login of a new account |

## When they stop

- Movie marked watched  
- Show fully watched  
- Title no longer on Wishlist or any personal list  

## Reading an alert card

Each alert is a card: poster, title (links to the title page), a colored **type tag** (New episode, Season out, Released, Now streaming), and when it fired.

- Episode alerts show **S#E# — episode title · aired date**, and where it streams as tags — **teal** = on one of your services, gray = elsewhere (kept current at view time).
- Episode/season alerts have a **Progress** button that opens the progress **side panel** in place — mark episodes watched without leaving Alerts. **Details** goes to the full title page.
- **Mark read/unread** dims or brightens the card; the nav badge counts unread.

## Turning types off

**Preferences → Alerts** — uncheck any type. Defaults are on.

## How they arrive

Written in the background: once shortly after the app starts, then about every `ALERTS_INTERVAL_HOURS` (default 6h). You see them next login or page refresh. Admins can run **Run alert check now** from the Admin dashboard.

- Episode detection uses Trakt's **My calendar** bulk feed — one call per run covers every watchlisted or in-progress show, so a show you **just added** alerts on the very next run. List-only shows (never watched, not watchlisted) get a per-show fallback check.
- If Trakt is rate-limiting (HTTP 429), the run backs off instead of scanning shows one by one — nothing is lost; the next run catches up within the 3-day window.
- First scan after install (or for a newly added show) only alerts episodes/seasons aired within the last **3 days** — older history is baselined silently, so you never get a flood of ancient episodes.

Streaming-service alerts need a free `TMDB_API_KEY` in `.env`.
