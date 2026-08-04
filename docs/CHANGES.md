# Changes log

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
