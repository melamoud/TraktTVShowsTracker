# Latest movies

Shows titles recently **added or changed in Trakt’s database**, newest Trakt activity first.

## Source

Uses Trakt’s official `/movies/updates` API — the closest public feed to “what just showed up / changed in Trakt’s DB”.

**Important:** Trakt does **not** expose a separate “first inserted into Trakt” timestamp. The same feed includes:

- brand-new titles entering Trakt’s DB, and  
- older titles when Trakt later edits their metadata  

Your **review marker** uses this Trakt DB activity time (not theatrical release date).

This is **not** the public release / “coming soon” calendar.

## Features

- **10 / 50 / 100** per page  
- **Hide watched** on by default  
- Preference highlights, watchlist/watched, review marker  
- Poster, description, genres  
- **Streaming:** read-only TMDB/JustWatch list (needs free `TMDB_API_KEY`)  
- **Alert when streaming** for in-app release notifications  

“Found on” is **not** on Latest — assign that on My movies/shows.

## Sync window

Trakt only returns about the **last 29–30 days** of DB updates. Older change history cannot be re-pulled. Titles already saved locally stay in this app.
