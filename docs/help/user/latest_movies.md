# Latest movies

Shows titles recently **added or changed in Trakt’s database**, newest Trakt activity first.

## Matches only + recent years (defaults)

Trakt can add **hundreds of updates per day**, and most are **metadata edits on old titles** — Trakt has **no** “first inserted” flag.

By default Latest applies two local filters:

1. **Recent years** — keep production year ≥ this year (or ≥ last year in Jan–Jun). Toggle **Include older years** to see classics that just got a DB edit.  
2. **Matches only** — purple genres/keywords. Toggle **All titles** for the unfiltered (but still year-filtered) feed.  

Without genres/keywords, Matches only is empty — use the setup wizard / Preferences, or All titles.

## Source

Uses Trakt’s official `/movies/updates` API — the closest public feed to “what just showed up / changed in Trakt’s DB”.

**Important:** Trakt does **not** expose a separate “first inserted into Trakt” timestamp. The same feed includes:

- brand-new titles entering Trakt’s DB, and  
- older titles when Trakt later edits their metadata  

Your **review marker** uses this Trakt DB activity time (not theatrical release date).

This is **not** the public release / “coming soon” calendar.

## How sync works

1. **First time** / **Refresh**: light pagination probe (`limit=1`), then **one newest** Trakt `/updates` page with `extended=full` (genres/overview for Matches-only). Does **not** sync your whole watchlist.  
2. **Later visits**: uses your local cache; at most a throttled 1-page newest refresh.  
3. **Older pages**: loaded **only** when you click **Load older Trakt page** — never invent empty UI pages.  

The review marker only **dims** titles already in cache; it is not a sync depth target anymore.

Trakt’s `/updates` API **cannot** filter by genre/keyword server-side. Matches-only filters locally after each page is cached (genres/overview come from `extended=full`).

## Features

- **Matches only / Show all**  
- **10 / 50 / 100** per page  
- **Hide watched** on by default  
- Preference highlights (genres/keywords only), **Add to lists…** / watched, review marker (set / clear)  
- Poster, description, genres  
- **Streaming:** read-only TMDB/JustWatch list (needs free `TMDB_API_KEY`)  

Collection alerts (release day, new streaming, episodes) are automatic for Wishlist / list titles — see [Alerts](release_alerts). “Found on” is **not** on Latest — assign that on My movies/shows.

## Sync window

Trakt only returns about the **last 29–30 days** of DB updates. Older change history cannot be re-pulled. Titles already saved locally stay in this app.

Trakt can record **thousands** of DB updates in a single day, so the first pages may all show today’s date when you use **Show all**. Prefer **Matches only** for day-to-day review.
