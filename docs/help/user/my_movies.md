# My movies

Movies on your Trakt **Wishlist** and **personal lists** (the ones you show in Preferences), with local metadata (poster, description, genres). Watch history alone does **not** put a title here.

Opening this page uses a local cache. Trakt is contacted at most every **N hours** (admin **Trakt read cache** TTL, default 2) per object, after **Refresh from Trakt**, or when an in-app write could not be applied locally. Watch / rate / list actions in this app update the same local rows that Latest, Recs, and Alerts read — they do not re-pull the title from Trakt. Adds you made only on trakt.tv appear after the TTL expires or a manual refresh. Sorted by in-progress first, then most recently watched; not-started titles last.

## Filters

- **Lists…** — which Wishlist / personal lists to include (same checklist style as Set lists)
- **Watched** — among those lists, watched titles only  
- **Both** — every title on the selected lists (watched and not)  
- **Unwatched** — among those lists, titles that are not watched yet
- **Search titles in this list…** — filters the full filtered set by title/year (backfills missing local titles first; not remembered; see [Search](search) for Trakt-wide search)
- **View: List / Newest aired / Weekly / Daily / Monthly** — switch to a **Newest aired** sort (movies sorted by release date, newest released first, future releases hidden; pins stay on top) or a Trakt-style **calendar** of upcoming releases limited to your current **Lists…** selection and status filter; click an entry to open the title. Mode is remembered.
- **Upcoming / Theater window / Streaming** — release & streaming availability (chips under the poster). Theater = public release within ±30 days; Upcoming = more than 30 days out; Streaming = TMDB lists a subscription/free vendor

## Paging

Long lists are paged (10 / 50 / 100 per page, same as Latest). Only the current page of titles is loaded and enriched.

Filter choices and page size are remembered for your account when you leave and come back.

## Actions

- **Pin / Unpin** — keep a title in the pinned group at the top (local only). In **Newest aired**, pins still sort by release date among themselves
- **Set lists…** — set Wishlist + Trakt personal list membership (checkboxes = actual membership; **Apply my defaults** / **Remove from all lists**)
- **Rate…** — set or clear a 1–10 Trakt rating (same as trakt.tv)

Open the title page for **Write review…** (posts a Trakt comment; optional spoiler). Episode reviews are only in the Progress panel for shows.
- **Favorite / Unfavorite** — add or remove from Trakt favorites
- **Mark watched / Unwatch** — syncs to Trakt (asks for confirmation first)
- **Streaming** / **Plays on your services** — TMDB availability (same as Latest); highlighted when it matches services in Preferences  
- **Found on…** — multi-select where *you* found it (local only; see [Streaming](streaming)). Each row has **Search** to open that service for the title without saving first.
- Open the title for full detail, IMDb, Trakt, trailer

List membership ↔ watched works both ways (mark watched from a list, or put a watched title onto lists).
