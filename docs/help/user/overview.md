# Getting started

TraktTV Shows Tracker helps you review newly listed movies and shows on Trakt, highlight titles that match your genres/keywords, and keep watch progress synced with your TraktTV account.

## Main areas

- **Latest movies / shows** — browse Trakt DB updates; defaults to **preference matches**; review marker
- **Recommended movies / shows** — personalized Trakt picks; genre categories; highlight services you own
- **Preferences** — your services, genres, keywords, **hidden genres**, favorite actors, which Trakt lists show in **Set lists…**, and **create / delete** personal lists on trakt.tv
- **My movies / My shows** — titles on the **Lists…** you pick (Wishlist + personal lists). Watch history alone does not put a title here. See [Wishlist vs lists](wishlist): Trakt **removes Wishlist after the first watch**, so in-progress / finished titles need a personal list
- **Search** — Trakt-wide title and/or actor search; actor / year / genres sit in **More filters**; defaults hide watched + already-listed titles. List pages have **Filter this page…** (titles already on that page) plus **Search actor** in More filters (opens this Search page)
- **Availability** — under-poster chips + filters for Upcoming (>30d), Theater window (±30d), and Streaming
- **Series progress** — mark seasons/episodes; **Rate / Review** dialog (rating + comment + optional watch); updates Trakt
- **Title detail** — open a movie/show page for cast (favorite / search titles by actor), **Write review…**, rate / favorite / lists. **← Back** returns to the list you came from (Search, My, Latest, Recs, Alerts)
- **Alerts** — automatic in-app alerts for collection titles (release date, new streaming, a season landing on a service, episodes/seasons), **Added to a list**, and **new titles with a favorite actor**. Pin a title, sort by time, group a show’s episodes; poster badge is Episode / Season / Streaming / Movie / List / Actor. Toggles in Preferences
- **Android app** — My Shows / My Movies / Search / Alerts / Progress, plus movie/show **title pages** (tap a card) and a home-screen **widget** (Shows / Movies / Alerts). Latest and Recommended stay on the website for now. See [Android app](android).

You must log in with TraktTV. There are no local passwords for normal users.

## Important notes

- A **loading overlay** appears whenever the app is talking to Trakt or navigating to a new page. Use **Stop** (or Escape) if it gets stuck; an in-flight request may still finish.
- Latest lists titles recently **added/changed in Trakt’s database** (`/updates` API). Trakt does not publish a separate “first inserted” date. See Help → Latest movies / Trakt sync limit.
- **Streaming** (TMDB) ≠ **Found on** (your choice). See Help → Streaming vs Found on.
- Trakt **Watchlist** is “not started yet.” The first episode (or movie play) **removes it from Wishlist**. Use a personal list to keep titles on My Shows/Movies. See [Wishlist vs lists](wishlist).
- Free `TMDB_API_KEY` unlocks Streaming lines and “added to a streaming service” alerts.
