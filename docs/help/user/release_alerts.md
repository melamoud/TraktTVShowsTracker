# Alerts

In-app messages under **Alerts** in the nav (badge = unread). By default they cover titles on your **Wishlist** only. Turn on **Alerts** for other lists under **Preferences → Trakt lists** if you want those too (park/archive lists can stay off).

This is separate from **Streaming vs Found on** (where a title plays / where you found it).

## What you can get

| Alert | Meaning |
|-------|---------|
| **Movie release date** | A listed movie’s release day arrives |
| **Added to a streaming service** | A **new** service brand starts carrying that title (one alert per brand). Channel/tier renames like “Paramount Plus Apple TV channel” after Premium do **not** re-alert |
| **New episode or season** | An episode aired; if a full season drops the same day, one season alert instead. A show premiere is announced by its S01E01 episode alert — there is no separate show “release” alert |
| **New user signed up** | Admins only — first login of a new account |

## When they stop

- Movie marked watched  
- Show **caught up** on aired episodes (Progress `watched / aired`, not a sticky “finished” flag). Streaming alerts pause when caught up; **new episode/season** alerts still use your calendar for watchlisted or in-progress shows so a new season is not missed. An episode alert does **not** mean the show is still on Wishlist — Trakt may already have removed it after the first watch ([Wishlist vs lists](wishlist))  
- Title no longer on any **alert-enabled** list (Preferences → Trakt lists → **Alerts**; default Wishlist) 

A batch of episodes airing the same day only counts as a **season** alert when the **whole** season drops that day. If more episodes air later (weekly or a partial drop), you get **per-episode** alerts instead.

## Reading an alert card

Each alert is a compact card: poster with a badge for **what happened**, then the title.

| Badge | Meaning |
|-------|---------|
| **Episode** | One new episode (`S3E5`) — has **Progress** |
| **Season** | A full season dropped the same day (one alert, not one per episode) — has **Progress** |
| **Streaming** | The title appeared on a new service (not a new episode) — **Progress** still opens the show |
| **Movie** | Movie release or streaming |
| **Admin** | New user login |

Episode titles put the number in the name itself — **The Agency S3E5**. Type tags (New episode, Season out, Released, Now streaming) still sit on that line.

- Episode subtitle is the episode name and aired date. Movie **Released** / **Now streaming** alerts show the movie’s release date — not “Title is available on Service” (the service is the type tag plus streaming chips). **Also streaming** (other services) is its own row above **Found on** / **Plays on your services**, which share a line — **teal** = on one of your services, gray = elsewhere (kept current at view time).
- **Pin** a show or movie to keep *all* of its alerts at the top (including future episodes of that show). This is separate from pinning on My Shows / My Movies. Pinned titles stay time-ordered among themselves, then unpinned alerts follow.
- **Newest first** / **Oldest first** sorts by time. Choice is remembered. Pins still win over the clock.
- **Grouped by show** (default on) collapses several episode alerts for the same show into one row: poster, show title, and the unread **S#E#** list (oldest first). **Show N alerts** (▸) marks the row as expandable — tap it to indent each episode and **Progress** / **Mark read** / **Pin** them. Pin always applies to the **show**, not one episode. **Ungroup** shows every alert as its own row. Movies and admin alerts stay individual.
- Episode/season alerts have a **Progress** button that opens the progress **side panel** in place — mark episodes watched without leaving Alerts. **Details** goes to the full title page; **← Back** there returns to Alerts.
- **Mark read/unread** dims or brightens the card; the nav badge counts unread.
- On the next **alert refresh**, movie release/streaming alerts auto-mark read when the movie is watched on Trakt, and episode/season alerts auto-mark read when that episode (or every episode in the season drop) is watched on Trakt.
- **Immediately** when you click **Watch** / **Mark season watched** / **Mark watched** in this app (Progress or title cards), matching alerts for that episode/season/movie are marked read without waiting for the next refresh. On Android, the Alerts list also reloads when you return from Progress.
- **Hide read** (default on) — only unread alerts; toggle **Show read** to browse older ones. Choice is remembered.

## Turning types / lists off

**Preferences → Trakt lists → Alerts** — pick which lists generate alerts (default: Wishlist only).

**Preferences → Alerts** — uncheck any alert **type**. Defaults are on.

## How they arrive

Written in the background on the schedule under **Admin → Scheduler** (default: every 4 hours at :00 **America/New_York** — 12am / 4am / 8am / 12pm / 4pm / 8pm). You see them next login or page refresh. Admins can **Run alert check now** from Admin, Scheduler, or the Alerts page.

- Episode detection uses Trakt's **My calendar** bulk feed — one call per run covers every watchlisted or in-progress show, so a show you **just added** alerts on the very next run. List-only shows (never watched, not watchlisted) get a per-show fallback check.
- If Trakt is rate-limiting (HTTP 429), the run backs off instead of scanning shows one by one — nothing is lost; the next run catches up within the 3-day window.
- First scan after install (or for a newly added show) only alerts episodes/seasons aired within the last **3 days** — older history is baselined silently, so you never get a flood of ancient episodes.

Streaming-service alerts need a free `TMDB_API_KEY` in `.env`.
