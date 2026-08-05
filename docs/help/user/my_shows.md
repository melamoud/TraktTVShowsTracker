# My shows

Same as [My movies](my_movies) for series — **Lists…** checklist filter from Preferences, plus watched filters.

Extra status filter: **Unwatched episodes** — titles on your selected lists that are **not finished**, plus any watched show with incomplete progress. Fully watched shows (100%) drop out even if they stay on a list.

Sorted by in-progress first, then most recently watched (`last_watched_at` from Trakt). Titles you haven’t started are last.

Each show card shows **x / y episodes watched** and **Next: SxEy — title** when known. That summary is loaded for the **current page only** (a few Trakt progress calls) and cached ~12 hours — it is not part of full **Refresh from Trakt**, so Refresh stays about as fast as before.

Filter choices (status, Lists…, titles per page) are remembered for your account. Leaving My shows and coming back via the menu restores the same settings.

Opening the page uses a local cache, but it **auto-invalidates**: a cheap Trakt `/sync/last_activities` check runs on each visit, and watchlist / watched / lists re-sync when those timestamps advanced (e.g. you added a show on Trakt.tv). **Refresh from Trakt** forces a full re-pull. Sync is **read-only** — it never writes episode history.

**Mark watched** on a show confirms first: it marks **all** aired seasons/episodes on Trakt (same as Trakt’s whole-show watched). Prefer **Progress** → season/episode actions when you only finished one season.

Cards show **Streaming** / **Plays on your services** from TMDB (same layout as Latest), plus your local **Found on** choices.

Use **Progress** to open the episode screen (mark seasons/episodes; writes back to Trakt).
