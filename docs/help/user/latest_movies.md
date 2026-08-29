# Latest movies

Shows titles recently **added or changed in Trakt’s database**, newest Trakt activity first.

## Matches only + recent years (defaults)

Trakt can add **hundreds of updates per day**, and most are **metadata edits on old titles** — Trakt has **no** “first inserted” flag.

By default Latest applies two local filters:

1. **Recent years** — keep production year ≥ this year (or ≥ last year in Jan–Jun). Toggle **Include older years** to see classics that just got a DB edit.  
2. **Matches only** — purple genres/keywords. Toggle **All titles** for the unfiltered (but still year-filtered) feed. **Hide these genres** in Preferences still applies on All titles.  
3. **Hide list titles** — hides titles already saved to your personal Trakt lists (e.g., “TV Show Favs”) so Latest only surfaces new discoveries. Toggle **Show list titles** to see them again.  

Without genres/keywords, Matches only is empty — use the setup wizard / Preferences, or All titles.

**Filter this page…** filters the loaded Latest cache (after your year / match / watched filters) by title. **More filters** adds year, actor (jumps to Search), and genres. For Trakt-wide search, use nav **Search**.

**Upcoming / Theater window / Streaming** chips and filter pills use public release date (±30 / >30 days) and TMDB streaming lists.

## Source

Uses Trakt’s official `/movies/updates` API — the closest public feed to “what just showed up / changed in Trakt’s DB”.

**Important:** Trakt does **not** expose a separate “first inserted into Trakt” timestamp. The same feed includes:

- brand-new titles entering Trakt’s DB, and  
- older titles when Trakt later edits their metadata  

Your **review marker** uses this Trakt DB activity time (not theatrical release date). Unreleased titles must not jump to the top of Latest just because their cinema date is in the future.

This is **not** the public release / “coming soon” calendar.

## How sync works

1. **First time** / **Refresh**: light pagination probe (`limit=100`, no extended), then **one newest** Trakt `/updates` page with `extended=full` (genres/overview for Matches-only).  
2. **Later visits**: uses your local catalog cache; at most a throttled 1-page newest refresh (admin **Trakt read cache** TTL, default 2 hours).  
3. **Older pages**: loaded **only** when you click **Load older Trakt page** — never invent empty UI pages.  
4. **Hide watched**: uses the same local watched/wishlist cache as My pages (refreshed on that TTL, not on every click).  

The review marker only **dims** titles already in cache; it is not a sync depth target anymore.

Trakt’s `/updates` API **cannot** filter by genre/keyword server-side. Matches-only filters locally after each page is cached (genres/overview come from `extended=full`).

## Features

- **Matches only / Show all**  
- **10 / 50 / 100** per page  
- **Hide watched** on by default  
- **Hide list titles** on by default (personal Trakt lists)  
- Preference highlights (genres/keywords only), **Set lists…** / watched, **Rate…** / **Favorite**, review marker (set / clear), **Found on…**, **Hide recommendation**  
- Open a title for the full page; **← Back** returns here (not always to another Latest view)  
- Poster, description, genres  
- **Streaming:** read-only TMDB/JustWatch list (needs free `TMDB_API_KEY`)  
- **Hide recommendation:** sends Trakt a “Not interested” for this title; it disappears from future Trakt recommendations (the title stays in Latest until it pages out naturally)  

Filter and page-size choices are remembered for your account when you leave and return.

Collection alerts (release day, new streaming, episodes) are automatic for Wishlist / list titles — see [Alerts](release_alerts). **Found on** chips and **Found on…** work here the same as on My / Search (local labels; Search in the picker opens the service for that title).

## Sync window

Trakt only returns about the **last 29–30 days** of DB updates. Older change history cannot be re-pulled. Titles already saved locally stay in this app.

Trakt can record **thousands** of DB updates in a single day, so the first pages may all show today’s date when you use **Show all**. Prefer **Matches only** for day-to-day review.
