# Changes log

## 2026-08-06 — My lists sync / title search cache fixes

- In-app watchlist / list / watched / rating / favorite writes only advance matching Trakt activity fingerprint keys (no longer stamps unrelated remote watchlist/list adds as already synced)
- Failed watchlist/watched/list pulls do not advance the fingerprint (cache stays stale until a successful sync)
- My movies/shows title + availability filters backfill missing `CachedMedia` for the filtered set before applying `q=` / `avail=`

## 2026-08-06 — Ratings + favorites

- **Rate…** (1–10) and **Favorite / Unfavorite** on My, Latest, Recommended, Search, and title detail — syncs to Trakt like watchlist/watched
- Tags show current rating and Favorite; Refresh / auto-sync pulls `/sync/ratings` and `/sync/favorites`

## 2026-08-06 — Availability chips + filters

- Under-poster chips: **Upcoming** (>30 days out), **Theater window** (±30 days), **Streaming** / On your services
- Filter pills on My movies/shows, Latest, and Recommended (`avail=`)

## 2026-08-06 — Series progress side panel

- **Progress** / **Series progress** opens a right-hand drawer instead of leaving the page (My shows, Search, show detail)
- Episode/season watch actions refresh the panel in place; closing after edits reloads the list underneath

## 2026-08-05 — System-wide search

- Nav **Search** page: Trakt exact + broad title search with Latest-style cards (Add to lists / Watched / streaming)
- In-list **q** search on My movies/shows, Latest, and Recommended (full filtered set, not remembered)

## 2026-08-05 — Add to lists: clear-all remove fix

- Uncheck all lists + Save reliably removes Wishlist / personal-list membership (no longer re-paginates every Trakt list on save or dialog open)
- After list writes, refresh activities fingerprint so reload does not immediately full-sync (avoids 2nd-title rate-limit / hang)

## 2026-08-05 — My movies/shows: pin to top

- **Pin / Unpin** on My movies & My shows — local-only; pinned titles sort above everything else

## 2026-08-05 — My movies/shows: auto cache invalidation

- Opening My pages checks Trakt `/sync/last_activities` and re-syncs watchlist/watched/lists when they changed (no manual Refresh required for Trakt.tv edits)
- Latest + Recs also run that user-state check so Hide watched / wishlist tags stay accurate
- **Refresh from Trakt** remains as a force full pull

## 2026-08-05 — My movies/shows: streaming lines on cards

- My movies & My shows cards show **Streaming** / **Plays on your services** like Latest (TMDB providers)

## 2026-08-05 — My movies: Unwatched filter

- **Unwatched** pill on My movies — selected-list titles not marked watched

## 2026-08-05 — Remember screen filters per user

- Page size, watched/unwatched, Latest/Rec toggles, and My-list selection persist per user
- Returning via the nav (no query string) restores the last settings for that screen

## 2026-08-05 — My Shows cards: x/y watched + next episode

- Each show card shows episode counts and next-up (loaded for the current page only, cached ~12h)
- Full **Refresh from Trakt** still skips per-show progress (stays fast)

## 2026-08-05 — My Shows: Unwatched episodes excludes finished

- **Unwatched episodes** no longer keeps fully watched list titles (e.g. The Boys at 100%)
- Progress page writes real regular-season % into the local cache for that filter
- Refresh no longer invents `progress_percent=100` from play count alone

## 2026-08-05 — Guard whole-show Mark watched; season unwatch

- **Mark watched** / **Unwatch** on lists now confirm first; for shows they warn that *all* seasons go to (or leave) history
- Progress page: **Unwatch season** clears one season’s history without touching the rest
- Clarified that Refresh from Trakt is read-only (never writes history)

## 2026-08-05 — Series progress: mark season/series watched

- **Mark season watched** / **Mark series watched** on the progress page (Trakt history)
- Next-up row layout fixed so episode titles aren’t cramped beside Watch
- Season mark button sits outside the accordion so clicks reach the handler

## 2026-08-04 — Auto collection alerts

- Automatic in-app alerts for Wishlist + personal-list titles (release day, new streaming service, episode / full-season drop)
- Admin alert on a new user’s first login
- `AlertEvent` dedup/baselines; Preferences toggles per alert type
- Removed opt-in “Alert when streaming” button; Alerts page: mark read/unread, hide Mark-all when none unread
- Help: Alerts topic; Streaming vs Found on kept separate

## 2026-08-04 — My movies/shows: sort + no auto full-sync

- Sort by in-progress, then `last_watched_at` (newest first); never-started last
- Opening My pages uses local cache only; **Refresh from Trakt** does the slow full pull
- Watchlist fetch via `/users/me/watchlist/{type}/{sort_by}/{sort_how}` (`added/desc`)

## 2026-08-04 — Add to lists (Wishlist + personal Trakt lists)

- Replaced Add/Remove watchlist with **Add to lists…** multi-select (Wishlist first, then personal lists)
- Preferences: **Show in menu** vs **Auto-select** (Wishlist always shown; auto-select optional)
- My movies/shows: **Lists…** checklist filter (same prefs), paged 10/50/100 (current page only)
- Caches personal-list membership; syncs to Trakt watchlist + `/users/me/lists/…/items`

## 2026-08-04 — Trakt recommendations pages

- **Rec movies / Rec shows** — personalized Trakt `/recommendations` feed (same source as Trakt.tv)
- Genre category tabs from Preferences; hide wishlist / watched; “On my services” filter
- Clear **Plays on your services** highlight for owned streaming services (TMDB overlap)
- Purple genre/keyword match tags + Add to wishlist
- **Hide recommendation** (Trakt Not interested) removes a title from future picks
- Help docs + tests

## 2026-08-04 — Series progress specials vs watched counts

- Progress header counts / next-up ignore season 0 specials so finished season 1 no longer looks like “0 watched”
- Specials listed at the bottom; mark-watched fails on Trakt silent `added.episodes=0` no-ops

## 2026-08-02 — Latest lazy sync + numbered pager

- Removed hard 2-page Latest sync cap; first load pulls newest pages only (lazy older pages — avoids Trakt 429)  
- Cursor repair + seed oldest window page when cache is stuck on a single day  
- Numbered pager `< 1 2 3 … N >` on Latest (top and bottom); page count grows as older updates load  
- My lists: full Trakt watchlist/watched pagination (was truncating at ~10)  
- Note: Trakt `/updates` volume can be huge in one day — may redesign Latest if that stays painful  

## 2026-08-02 — Preference match = genres + keywords only

- Purple **Preference match** no longer includes owned streaming services (too many false positives)
- Help: Preferences page clarifies streaming is for Found-on / release alerts only

## 2026-08-02 — Phase II polish

- Latest: read-only **Streaming:** (TMDB); removed Found-on from Latest  
- My lists: multi-select Found-on with provider highlights; watchlist↔watched; default Wishlist  
- Local poster cache (Trakt forbids CDN hotlinking); detail/list enrich from `extended=full`  
- Admin: **Run release check now**; release-alert unit test  
- Help/docs + `docs/DEPLOYMENT.md` for tvtracker.melamoud.com  

## 2026-08-02 — Reverted Latest to Trakt DB updates (not release calendar)

- User intent is **Trakt DB add/change time**, not coming-soon releases — restored `/movies|/shows/updates`
- Kept hide-watched default + docs that Trakt has no separate `created_at`

## 2026-08-02 — Prefs custom services + help for 30-day limit

- Fixed saving/display of user custom streaming services (URL field no longer blocks submit; customs listed with remove)
- Documented Trakt ~30-day updates API limitation in Help / architecture

## 2026-08-02 — Catalog sync fix

- Trakt `/movies|/shows/updates` returns `[]` if `start_date` is older than ~29 days; sync now clamps the window
- Updates are oldest-first; sync now reads the **last** pages so “Latest” shows the newest Trakt activity
- Fixed Jinja typo on latest media overview truncation
- Login uses Trakt `ids.uuid` / username (numeric `ids.trakt` is often absent on `/users/settings`)

## 2026-08-02 — Initial scaffold (Phase 1)

- Created Flask + SQLite application mirroring AudioBooksReview patterns
- Trakt OAuth login; admin bootstrap via `ADMIN_TRAKT_USERNAMES`
- Latest movies/shows catalog with preference highlights, watchlist/watched actions, review markers
- User preferences (streaming services, genres, keywords) + custom service suggestions
- My movies / my shows filters; series progress with episode write-back
- TMDB watch-provider cache (US) + local “found on” labels + in-app release alerts
- Admin user management (disable, revoke sessions, delete local data, promote/demote)
- Help system (`docs/help/user|admin`), README, setup/architecture docs
- `run.bat` / `stop.bat` / `scripts/*`, pytest suite with mocked Trakt
- Git repository initialized (GitHub remote: create `melamoud/TraktTVShowsTracker` when `gh` is available)
