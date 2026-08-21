# My shows

Same as [My movies](my_movies) for series — only titles on your selected **Lists…**, with watched / unwatched as status filters inside that set.

**Trakt Watchlist warning:** marking **any** episode watched **removes the whole show from Wishlist** (you cannot turn that off). My Shows then loses it unless it is also on a **personal list** (e.g. TV Show Favs). **Mark read** on an alert does not change lists. See [Wishlist vs lists](wishlist).

Extra status filter: **Unwatched episodes** — selected-list titles that are **not finished**. Fully watched shows (100%) drop out even if they stay on a list.

Sorted by in-progress first, then most recently watched (`last_watched_at` from Trakt). Titles you haven’t started are last.

Each show card shows **x / y episodes watched** and **Next: SxEy — title · air date** when known. This data is maintained by the background media job (runs every ~6 hours and after **Refresh from Trakt**), not at page load — so pages render instantly from cache. A show you just added gets its first data within a minute of the sync that discovers it (a few titles per sync), or on the next job run.

Filter choices (status, Lists…, titles per page) are remembered for your account. Leaving My shows and coming back via the menu restores the same settings.

**View: List / Newest aired / Weekly / Daily / Monthly** — switch between the normal title rows, a **Newest aired** sort (shows sorted by the air date of their latest episode — including shows you’re caught up on — movies by release date; future titles hidden), and a Trakt-style **calendar**. The calendar uses Trakt’s **My calendar** limited to your current **Lists…** selection and status filter; click an entry to open the title. View modes are remembered. **Newest aired** is a pure cache view: the background job keeps last-aired dates fresh (33 days back / 33 ahead via My calendar for watchlisted shows, plus per-show checks for list-only titles), so the page loads instantly even on big collections. Pins stay on top.

**Filter this page…** filters by title across the full filtered set (query is not remembered). **More filters** adds year, actor (jumps to Search), and genres. Missing local titles are backfilled from Trakt before the filter runs. For titles not on your lists yet, use nav **Search**.

**Upcoming / Theater window / Streaming** chips sit under the poster; the same names are filter pills (Theater = ±30 days, Upcoming = >30 days out). The availability filter is remembered like status and view.

Opening the page uses a local cache shared with Progress, Latest tags, and Alerts. **Watchlist and personal-list membership** are checked against Trakt `last_activities` on each My Shows load (cheap) and refreshed when those timestamps moved — including moves you made on trakt.tv. Progress/calendar still use the admin **Trakt read cache** TTL (default 2 hours). In-app watch / rate / list actions update those same objects immediately. **Refresh from Trakt** forces a full re-pull of membership **and** queues a background pass over episode/progress data (results appear within a minute). Sync is **read-only** — it never writes episode history. **Set lists…** is the write path: it refreshes membership before showing checkboxes, and unchecking Wishlist or a default list (e.g. TV Show Favs) always removes it on Trakt so a later sync cannot put the title back on this page.

**Pin** keeps a show in the pinned group at the top (local only — for “watching now” / “soon”). In **List**, the newest pin wins among pins. In **Newest aired**, pins stay above unpinned titles, but among pins the latest episode date still wins. **Unpin** returns it to normal sort.

**Rate…** (1–10) and **Favorite / Unfavorite** sync to Trakt the same way as on trakt.tv.

**Mark watched** on a show confirms first: it marks **all** aired seasons/episodes on Trakt (same as Trakt’s whole-show watched). Prefer **Progress** → season/episode actions when you only finished one season.

Cards show **Streaming** / **Plays on your services** from TMDB (same layout as Latest), plus your local **Found on** choices.

Use **Progress** to open the episode panel beside the list (Watch / **Rate / Review** dialog; writes back to Trakt). See [Series progress](series_progress). Open a show’s title page for **Write review…** on the series itself.
