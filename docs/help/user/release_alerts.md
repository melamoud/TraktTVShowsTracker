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
- Show **caught up** on aired episodes (Progress `watched / aired`, not a sticky “finished” flag). Streaming alerts pause when caught up; **new episode/season** alerts still use your calendar for watchlisted or in-progress shows so a new season is not missed  
- Title no longer on Wishlist or any personal list  

A batch of episodes airing the same day only counts as a **season** alert when the **whole** season drops that day. If more episodes air later (weekly or a partial drop), you get **per-episode** alerts instead.

## Reading an alert card

Each alert is a card: poster, title (links to the title page), a colored **type tag** (New episode, Season out, Released, Now streaming), and when it fired.

- Episode alerts show **S#E# — episode title · aired date**, and where it streams as tags — **teal** = on one of your services, gray = elsewhere (kept current at view time).
- Episode/season alerts have a **Progress** button that opens the progress **side panel** in place — mark episodes watched without leaving Alerts. **Details** goes to the full title page.
- **Mark read/unread** dims or brightens the card; the nav badge counts unread.
- On the next **alert refresh**, movie release/streaming alerts auto-mark read when the movie is watched on Trakt, and episode/season alerts auto-mark read when that episode (or every episode in the season drop) is watched on Trakt.
- **Immediately** when you click **Watch** / **Mark season watched** / **Mark watched** in this app (Progress or title cards), matching alerts for that episode/season/movie are marked read without waiting for the next refresh.
- **Hide read** (default on) — only unread alerts; toggle **Show read** to browse older ones. Choice is remembered.

## Turning types off

**Preferences → Alerts** — uncheck any type. Defaults are on.

## How they arrive

Written in the background on the schedule under **Admin → Scheduler** (default: every 4 hours at :00 **America/New_York** — 12am / 4am / 8am / 12pm / 4pm / 8pm). You see them next login or page refresh. Admins can **Run alert check now** from Admin, Scheduler, or the Alerts page.

- Episode detection uses Trakt's **My calendar** bulk feed — one call per run covers every watchlisted or in-progress show, so a show you **just added** alerts on the very next run. List-only shows (never watched, not watchlisted) get a per-show fallback check.
- If Trakt is rate-limiting (HTTP 429), the run backs off instead of scanning shows one by one — nothing is lost; the next run catches up within the 3-day window.
- First scan after install (or for a newly added show) only alerts episodes/seasons aired within the last **3 days** — older history is baselined silently, so you never get a flood of ancient episodes.

Streaming-service alerts need a free `TMDB_API_KEY` in `.env`.
