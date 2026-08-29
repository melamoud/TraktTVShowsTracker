# Search

## Trakt-wide Search

Use **Search** in the top navigation to find movies and shows in Trakt’s database (not only titles you already track).

1. Type a **title** (at least **2 characters**) in the top box
2. Open **More filters** for **Actor** (name or favorite), **Year**, and **Genres** — Actor sits on the same row as Year
3. Use the **Movies** / **Shows** pills (both on by default) — tap one to search that type only; tap again via the other pill to restore both
4. Results use the same card layout as Latest: overview, genres, streaming lines, **Found on**, preference tags, watchlist/watched status
5. **Set lists…** / **Mark watched** / **Rate…** / **Favorite** / **Found on…** work the same as elsewhere; shows also link to **Progress**. Open a result for the **title page**; **← Back** there returns to this Search (browser **Back** does too).

Exact title matches are listed before broader fuzzy hits. Actor search uses that person’s Trakt **cast** filmography (newest first; crew credits are skipped). Title + actor together keeps only that actor’s titles whose name matches the title box.

Trakt search results are cached locally for the admin **Trakt read cache** TTL (default 2 hours), same as My / Recs — browser **Back** reuses that cache instead of calling Trakt again. **Refresh from Trakt** on the Search page forces a new pull. Hide-watched / lists / year / genre still apply locally on each view.

You can start an actor search from:

- **More filters** on Search, Latest, Rec, and My (Actor is next to Year; list pages have **Search actor**, which always opens **this** Search page)
- An actor’s name or **Titles** on a movie/show detail Cast list
- An actor’s name or **Titles** under Preferences → Favorite actors

### Filters (remembered)

Defaults keep Search focused on new discoveries:

- **Not watched** (default) — hides titles you already marked watched. Use **Show watched** to include them.
- **Not in lists** (default) — hides titles on **Wishlist** or any personal Trakt list. Use **In lists** to include them.

- **Actor** — name or a favorite-actor pick (Trakt cast filmography). Optional; can be used with or without a title.
- **Year** — `2018` or `2015-2020` (production year, else release year). Narrows hits.
- **Genres** — pick one or more; a title matches if it has **any** selected genre.

Year and genres are remembered for your next Search visit (same as Latest / My filters). They apply to both title search and actor filmography. Actor is not remembered as a default filter.

## Search within a page

My movies / My shows, Latest, and Recommended each have a **Filter this page…** box in the toolbar, plus **More filters** (year, actor, genres) that stay collapsed until you open them.

- Filters the **current page’s filters** (lists, watched, matches, etc.) by title, year, and/or genres
- Year/genres can stand alone on these pages (the list is already loaded)
- Searches the **full filtered set**, then paginates — not only the current page
- Title query is **not** remembered when you leave the page (clear with **Clear**, or drop `q` from the URL)

**Search actor** in More filters jumps to the main Search page (so hide-watched, lists, year, and genres still apply). It is not an in-page filter.

To find something you do not already have on a list, use the nav **Search** page instead.
