# Getting started

TraktTV Shows Tracker helps you review newly listed movies and shows on Trakt, highlight titles that match your genres/keywords, and keep watch progress synced with your TraktTV account.

## Main areas

- **Latest movies / shows** — browse Trakt DB updates; defaults to **preference matches**; review marker
- **Recommended movies / shows** — personalized Trakt picks; genre categories; highlight services you own
- **Preferences** — your services, genres, keywords, which Trakt lists show in **Add to lists…**
- **My movies / My shows** — multi-select Wishlist + personal lists / watched / unwatched; **Rate…** + **Favorite**; TMDB **Streaming** lines + local **Found on…**; filters remembered; cache auto-refreshes when Trakt activity changes
- **Search** — Trakt-wide title search (lists / watched / rate / favorite); each list page also has in-list title search
- **Availability** — under-poster chips + filters for Upcoming (>30d), Theater window (±30d), and Streaming
- **Series progress** — mark seasons/episodes (and unwatch a season); updates Trakt
- **Alerts** — automatic in-app alerts for collection titles (release date, new streaming, episodes/seasons); toggles in Preferences

You must log in with TraktTV. There are no local passwords for normal users.

## Important notes

- A **loading overlay** appears whenever the app is talking to Trakt or navigating to a new page; wait for it to clear before clicking again.
- Latest lists titles recently **added/changed in Trakt’s database** (`/updates` API). Trakt does not publish a separate “first inserted” date. See Help → Latest movies / Trakt sync limit.
- **Streaming** (TMDB) ≠ **Found on** (your choice). See Help → Streaming vs Found on.
- Free `TMDB_API_KEY` unlocks Streaming lines and “added to a streaming service” alerts.
