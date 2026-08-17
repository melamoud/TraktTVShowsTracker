# Getting started

TraktTV Shows Tracker helps you review newly listed movies and shows on Trakt, highlight titles that match your genres/keywords, and keep watch progress synced with your TraktTV account.

## Main areas

- **Latest movies / shows** — browse Trakt DB updates; defaults to **preference matches**; review marker
- **Recommended movies / shows** — personalized Trakt picks; genre categories; highlight services you own
- **Preferences** — your services, genres, keywords, favorite actors, which Trakt lists show in **Set lists…**
- **My movies / My shows** — multi-select Wishlist + personal lists; **Watched / Both / Unwatched** status filters inside those lists; **Rate…** + **Favorite**; TMDB **Streaming** lines + local **Found on…**; filters remembered; pages render from a shared cache (Trakt at most every few hours, or after Refresh / a write that could not be applied locally)
- **Search** — Trakt-wide title and/or actor search; actor / year / genres sit in **More filters**; defaults hide watched + already-listed titles; each list page also has in-list title search plus **Search actor** in More filters
- **Availability** — under-poster chips + filters for Upcoming (>30d), Theater window (±30d), and Streaming
- **Series progress** — mark seasons/episodes; **Rate / Review** dialog (rating + comment + optional watch); updates Trakt
- **Title detail** — open a movie/show page for cast (favorite / search titles by actor), **Write review…**, rate / favorite / lists. **← Back** returns to the list you came from (Search, My, Latest, Recs, Alerts)
- **Alerts** — automatic in-app alerts for collection titles (release date, new streaming, episodes/seasons); toggles in Preferences
- **Android app** — My Shows / My Movies / Search / Alerts / Progress, plus movie/show **title pages** (tap a card). Latest and Recommended stay on the website for now. See [Android app](android).

You must log in with TraktTV. There are no local passwords for normal users.

## Important notes

- A **loading overlay** appears whenever the app is talking to Trakt or navigating to a new page. Use **Stop** (or Escape) if it gets stuck; an in-flight request may still finish.
- Latest lists titles recently **added/changed in Trakt’s database** (`/updates` API). Trakt does not publish a separate “first inserted” date. See Help → Latest movies / Trakt sync limit.
- **Streaming** (TMDB) ≠ **Found on** (your choice). See Help → Streaming vs Found on.
- Free `TMDB_API_KEY` unlocks Streaming lines and “added to a streaming service” alerts.
