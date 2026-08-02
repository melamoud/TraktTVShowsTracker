# Latest movies

Shows titles recently **added or changed in Trakt’s database**, newest Trakt activity first.

## Source

Uses Trakt’s official `/movies/updates` API — the closest public feed to “what just showed up / changed in Trakt’s DB”.

**Important:** Trakt does **not** expose a separate “first inserted into Trakt” timestamp. The same feed includes:

- brand-new titles entering Trakt’s DB, and  
- older titles when Trakt later edits their metadata  

Your **review marker** uses this Trakt DB activity time (not theatrical release date).

This is **not** the public release / “coming soon” calendar.

## How sync works

1. **First time** (empty cache): pulls the **newest** Trakt update pages (a few hundred titles) so the page stays fast.  
2. **Later visits**: uses your local cache; occasionally refreshes the newest page; walks older pages only until **your** review marker is covered.  
3. **Older pages**: loaded **lazily** when you move to a later list page — never the whole ~30-day window in one click (that rate-limits Trakt).  

Use the numbered pager **`< 1 2 3 … N >`** (top and bottom) to jump pages. The page count is only what’s loaded locally so far — it can grow as older Trakt updates are fetched.

## Features

- **10 / 50 / 100** per page  
- **Hide watched** on by default  
- Preference highlights (genres/keywords only), watchlist/watched, review marker  
- Poster, description, genres  
- **Streaming:** read-only TMDB/JustWatch list (needs free `TMDB_API_KEY`)  
- **Alert when streaming** for in-app release notifications  

“Found on” is **not** on Latest — assign that on My movies/shows.

## Sync window

Trakt only returns about the **last 29–30 days** of DB updates. Older change history cannot be re-pulled. Titles already saved locally stay in this app.

Trakt can record **thousands** of DB updates in a single day, so the first pages may all show today’s date. Jump to later/last pages for older activity. If that stays too noisy day-to-day, we’ll revisit the Latest design.
