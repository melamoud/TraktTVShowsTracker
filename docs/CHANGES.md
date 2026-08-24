# Changes log

## 2026-08-23 — Calendar, progress counts, and Theater use local air times

- My Calendar and **Next: SxEy · date** store Trakt episode times in the scheduler timezone (`01:00Z` → previous evening), not the UTC calendar day
- Last-aired no longer copies *today’s* date-only calendar row (that counted a 9pm episode all afternoon); seasons fetch supplies the clock time
- **x / y episodes watched** and caught-up / streaming-alert pause ignore Trakt’s UTC `aired` count until the episode has aired locally
- Theater / Upcoming chips ignore a show `released_at` that is years after the premiere year (Outer Banks S5 date was not a theatrical window). Run `python scripts/fix_show_released_at.py` once per environment to clear those rows

## 2026-08-23 — Local air dates, merged streaming alerts, Newest aired sort

- Episode air times display and sort in the scheduler timezone (America/New_York): Trakt’s `01:00Z` is the previous evening, not tomorrow
- Progress no longer labels a still-future local air time as already aired just because Trakt’s UTC progress flag flipped
- Same-title **Now streaming** alerts collapse to one card listing every vendor; unread if any vendor is unread; Mark read clears them all
- Newest aired uses that local last-episode day (Lanterns was under Outer Banks because last-aired was empty and fell back to the Aug 17 premiere)

## 2026-08-23 — Newest aired hid shows like Lanterns

- Newest aired dropped shows whose last-aired date was never cached (first seed ran before premiere, then waited 30 days)
- Those shows now appear from episode counts / premiere date, and the cache job re-seeds as soon as progress knows episodes aired

## 2026-08-23 — No confirm on Hide recommendation or Mark watched

- Website **Hide recommendation** and **Mark watched** run immediately (no approve dialog). **Unwatch** still confirms

## 2026-08-23 — Android home-screen widget

- Add a resizable **TV Tracker** widget with **Shows Progress**, **Movies**, and **Alerts** (switch on the widget). Header shows the app icon and **TV Tracker ·** mode
- Shows: newest aired, one line per show with a next episode to watch (caught-up shows are hidden); remaining count; checkmark marks that episode after confirm
- Movies: newest aired; checkmark marks the movie watched after confirm
- Alerts: grouped by show; tap the arrow to expand. Title/poster opens the app on that title
- List scrolls. Does not change the website’s List vs Newest aired setting

## 2026-08-23 — Latest was stuck: wrong Trakt page + future sort dates

- Newest catalog refresh used a `limit=1` pagination probe, so it asked Trakt for page ~137000 (item count) instead of the real newest page of 100. No new titles landed for days
- Theatrical dates (e.g. Avengers: Doomsday in December) were overwriting Latest’s sort key, pinning unreleased 2026 titles at the top. Sort is Trakt DB `updated_at` again
- Watchlist/list sync no longer rewrites that sort key or replaces catalog JSON with a list payload

## 2026-08-22 — Alert when you add a title to a list

- Adding a movie or show to Wishlist or a personal list (Set lists or Wishlist) creates an in-app **Added to a list** alert immediately
- Opt out under Preferences → Alerts → **Added to a list** (default on)

## 2026-08-22 — Android alert Progress stays one line

- Grouped **Show N alerts** no longer squeezes **Progress** onto two lines (`progre` / `ss`)
- **Progress** matches the height of **Mark read** and **Pin** on episode rows

## 2026-08-22 — Create and delete Trakt lists from Preferences

- Preferences → **Trakt lists** can **Create on Trakt** (private personal list) and **Delete** a list
- Both write to trakt.tv; Delete also clears local membership and Alerts/auto-select checkmarks for that list

## 2026-08-22 — Alerts pin, sort, type, and show groups

- **Pin** a show or movie on Alerts (website and Android) so all of that title’s alerts — including future episodes — stay above unpinned ones (the show, not one episode)
- **Newest first** / **Oldest first** time sort is remembered (app + web); pins still float to the top
- Poster badge is **Episode / Season / Streaming / Movie / Admin**; episode titles include **S3E5**
- **Grouped by show** (default) collapses a show’s episode alerts; **Show N alerts** expands them to indent and handle one by one
- **Progress** is on every show-linked alert (including Streaming). Watched episode alerts clear when you open Alerts

## 2026-08-20 — Wishlist vs personal lists (Help)

- Help documents Trakt’s Watchlist rule: the first movie play or **any one episode** removes the title from Wishlist. Use a personal list (e.g. TV Show Favs) for titles you want to keep on My Shows/Movies
- New Help topic **Wishlist vs lists**; linked from Getting started, Preferences, My movies/shows, Progress, and Alerts

## 2026-08-19 — Streaming alerts ignore TMDB channel renames

- **Now on …** alerts key on the service brand (e.g. Paramount Plus), not packaging strings like “Apple TV channel” / Premium / Essential
- Stops false alerts when TMDB renames or adds another channel listing for a service you already saw (e.g. Red Alert)

## 2026-08-19 — Choose which lists generate alerts

- Preferences → **Trakt lists** has an **Alerts** column. Default is **Wishlist only**, so park/archive lists stay quiet
- Check a personal list there if you still want release / streaming / episode alerts for those titles
- Global alert-type toggles (release, streaming, episodes) still apply on top

## 2026-08-18 — Shorter page copy; Help on each screen

- Dropped the gray intro under each heading. A **?** next to the title opens that screen’s Help page
- List pages use **Filter this page…** (not Search) so it is obvious they do not find new titles; nav **Search** is still Trakt-wide
- Confusing pills and buttons have tooltips (Matches only, Lists…, Hide read, Search actor, and similar)

## 2026-08-17 — Title-page Back returns to Search (and other lists)

- The in-app **← Back** on a movie/show title page goes to the page you opened it from (Search, My, Latest, Recs, Alerts), not always Latest movies/shows

## 2026-08-16 — Don’t put dropped shows back on Wishlist

- My Shows/Movies always check Trakt `last_activities` (the 2h cache TTL no longer skips that). Moving Silo / Daredevil / etc. off Wishlist onto a “stop watching” list on trakt.tv was invisible for hours; opening **Set lists** and Save then wrote the old ticks back to Trakt
- Unchecking Wishlist **or** a personal list (e.g. TV Show Favs) on Save always removes it on Trakt, even if the local row already said off — a later sync was putting those titles back on My Shows
- After an in-app list save, store `last_activities` so the next page load does not full-pull lists and re-import a lagging Trakt GET

## 2026-08-16 — Set Found on from Android lists

- My Shows, My Movies, and Search cards can set **Found on…** from the ⋮ menu (same picker as the website and the title page)
- List and Search JSON include `found_on_choices`; the app can also load them from `GET /api/v1/found-on/choices`

## 2026-08-16 — Compact alert cards

- Alerts put episode name and air date on the title line; movies show the release date (not “available on”)
- Also streaming sits above Found on / Plays on (those two share a row); older episode “Available on:” suffixes are hidden

## 2026-08-16 — Database backup in a private repo

- Live `instance/trakttv.db` is no longer part of the code repo. Backup with `push-db.bat` to the private `TraktTVShowsTracker-db` repo. The app path is unchanged.

## 2026-08-16 — Android movie and show title pages

- Tap a title on My Shows, My Movies, Search, or Alerts to open the same kind of page as the website: poster, overview, genres, streaming, Found on, actions, and cast
- Lists, rate, favorite, watched, Found on…, write review, and series progress work from that page; IMDb / Trailer / Homepage / Trakt open in the browser
- Cast **Titles** jumps to Search for that actor; **Favorite** is the same local favorite-actor toggle as Preferences

## 2026-08-16 — Actor lives in More filters (next to Year)

- Search, Latest, Rec, and My put **Actor** in **More filters** on the Year row so the toolbar stays one line
- List pages still jump to Search via **Search actor**; Search uses the same form as title / year / genres

## 2026-08-16 — Search Back uses the Trakt read cache

- Title and actor Search results are stored locally for the admin TTL (same as Recs / My)
- Browser Back (and repeating the same query) no longer re-hits Trakt; **Refresh from Trakt** on Search forces a new pull

## 2026-08-16 — Search movies/shows by actor

- Search accepts an actor name or a favorite-actor pick (plus optional title); results use the same hide-watched / lists / year / genre / type filters
- Latest, Rec, and My toolbars can jump to that Search; Cast and Preferences actor names have a **Titles** link

## 2026-08-15 — Android: remember filters; Found on opens the service

- The app no longer sends default My / Search / Alerts filters on first load (that was overwriting the saved website choices). Changing a filter still saves it for both app and web
- Availability (Upcoming / Theater / Streaming) is remembered the same way as status and List vs Newest aired
- **Found on** and streaming chips on the app are links, same as the website (title search when the service has one)

## 2026-08-15 — Found on on Android alerts and My cards

- Alert cards resolve Found on even for older rows that only stored the show name (no trakt id)
- My Shows / Search cards now show **Found on** the same way as the website

## 2026-08-15 — Android: last aired vs next episode

- Alert cards and My Shows use **Latest aired** for the episode that already aired; the upcoming one is labeled **Next:** with its date (same as the website)

## 2026-08-15 — Search year + genre filters

- Main Search (web + Android) has **Year** (`2018` or `2015-2020`) and multi-select **Genres** (match any). A title is still required; filters narrow Trakt hits locally
- My / Latest / Rec hide the same filters under **More filters** so they do not take space until needed; year/genre can stand alone there
- Choices are remembered per page like other view filters

## 2026-08-15 — Newest aired: among pins, still newest episode/release first

- Pin only lifts titles above unpinned ones. Two pinned shows (or movies) now sort by last aired / release date, not by who was pinned last

## 2026-08-15 — Newest aired sort matches pin + latest episode/release

- **Newest aired** is newest-first (shows: last episode air date; movies: release date) with pins still on top — same on the website and Android
- Caught-up shows stay in that view; they used to disappear, which made the sort look broken
- Switching List ↔ Newest aired reloads from the server; the Android app no longer sends `display=list` on first load (that overwrote the saved view and could race the tap)

## 2026-08-14 — GitHub screenshots

- README (and Android README) show My Shows, Progress, Recommended Movies, Alerts, and the Android My Shows screen

## 2026-08-14 — Non-commercial license

- Repository is licensed under PolyForm Noncommercial 1.0.0 (copyright Nir Melamoud). Commercial use needs written permission.

## 2026-08-14 — Android launcher icon

- Home-screen icon is the TV + radar mark instead of the placeholder T

## 2026-08-14 — Android: Alerts update after Progress; pull-to-refresh

- Marking an episode or season watched on Progress reloads Alerts (and the unread badge) as soon as you go back — the list no longer stays stale until you kill the app
- Every screen can pull down to refresh, or tap the refresh icon. That reloads from the TV Tracker server, not a full Trakt pull

## 2026-08-14 — Found on on alert cards

- Alerts (website and Android) show **Found on** from the title, plus labeled Streaming / Plays on your services — same as My / title pages

## 2026-08-13 — Android cards and filters compacted

- My / Search filters are dropdowns with checkmarks (one button each) instead of chip rows
- Title cards keep **Progress** and **Watch**; pin / lists / rate / favorite live in the ⋮ menu

## 2026-08-13 — Android app (My / Search / Alerts / Progress)

- Native Kotlin client in `android/` talks to `https://tvtracker.melamoud.com:8300` the same way AudioBooks Review does (HTTPS, bundled cert, cookie session)
- Login is Trakt OAuth in a Custom Tab, then a one-time token (`tvtracker://oauth`) becomes a Flask session
- `/api/v1` JSON for My movies/shows, Search, Progress, Alerts, and the existing list/watch/rate/favorite writes
- Latest and Recommended screens are not in this build

## 2026-08-13 — Trakt call log (source + user)

- Every cache object decision is logged as `Cache user_media hit user=friend calls=0 source=http GET /my/shows` (also `probe` / `fetch` with `calls=` for Trakt HTTP count)
- Scheduler catalog sync, alerts, and progress jobs log the same way (`reason=scheduler` / `alerts` / `job`) so page-load hits are not mistaken for “Trakt was never called”
- HTTP 429 / 4xx are still logged as warnings; successful per-request Trakt calls are not
- Admins can watch this live from **Admin → Trakt cache log**

## 2026-08-13 — Cache-first Trakt reads

- Page loads (including browser Back) read local SQLite for watchlist, lists, calendar, progress, recommendations, and Search results
- Trakt is contacted when that **object** is older than the admin TTL (default 2 hours, **Admin → Scheduler**), after **Refresh from Trakt**, or when an in-app write could not update the local object
- Progress / My / Alerts share one show-progress cache — marking an episode watched updates card counts and alert cleanup without a follow-up Trakt GET
- In-app writes no longer probe `/sync/last_activities`; changes made only on trakt.tv appear at the next TTL expiry or manual refresh

## 2026-08-13 — Alerts auto-read when you watch

- On each alert refresh, unread **movie release/streaming** alerts mark read if the movie is watched
- Unread **episode** alerts mark read when that episode is watched on Trakt; **season** alerts when every episode in the drop is watched
- Clicking **Watch** (Progress), **Mark season watched**, or **Mark watched** in the app also marks matching alerts read immediately

## 2026-08-13 — Progress drawer survives Trakt rate limits

- List membership sync no longer fetches seasons for every personal-list show (that loop kept calling Trakt after HTTP 429 and starved Progress)
- Remaining batch work (list items, title backfill) stops on the first 429
- Short burst 429s retry once; quota 429s fail fast instead of blocking the worker
- Progress panel returns 429 with a **Retry** button instead of a 502 traceback

## 2026-08-12 — Trakt link on every title card

- Latest / Recommended / Search / My cards now include a **Trakt** button (same as title detail), next to IMDb / Trailer

## 2026-08-12 — Search: hide watched / list titles by default

- Search filters: **Not watched** and **Not in lists** (Wishlist + personal lists), both on by default
- Choices remembered like Latest / My; **Show watched** / **In lists** to include them again
- **Movies** / **Shows** are toggle pills on the same filter row (both on by default) instead of a dropdown

## 2026-08-12 — Cast + favorite actors

- Title detail shows Trakt cast (main few, expand for all) with local **☆ Favorite** per actor
- Favorite actors managed in Preferences
- Cast headshots: one TMDB credits call per title; each person image cached once under `instance/actor_cache` and reused
- Ready for a future alert/highlight on new titles featuring your actors (not built yet)

## 2026-08-12 — Show catch-up is dynamic (no stalled 100% alerts)

- Alerts treat a show as finished only from Progress episode counts (or a Progress-stamped 100%), not a bare cached `progress_percent=100`
- Episode calendar alerts still run for watchlist/watched shows so a new season is not skipped by stale catch-up
- Partial same-day drops (some episodes aired, more later) alert per episode, not as a full-season drop
- **Mark series watched** / show Watch no longer invents local show `progress_percent=100` — % comes from Progress aired/completed

## 2026-08-12 — Fix alerts scheduler boot + 4h EST clock

- Scheduler now starts inside an app context (was silently failing since Aug 9: “Working outside of application context”)
- Media alerts default: every **4 hours at :00 America/New_York** (12am/4am/8am/12pm/4pm/8pm) — no run 2 minutes after restart
- Admins can force **Run alert check now** from Admin, Scheduler, or the Alerts page
- Alert job logs under the `app` logger so runs show up in `logs/app.log`

## 2026-08-11 — Found on dialog: Search per service

- **Found on…** dialog: each service row has a **Search** link that opens that site for the title (same URLs as chips) without selecting/saving first

## 2026-08-11 — Disney+ chips use Google site search

- Disney+ no longer deep-links to `disneyplus.com/search` (404); **Found on** / **Plays on** open a Google `site:disneyplus.com` title search instead

## 2026-08-11 — Progress air dates readable + trust Trakt aired flag

- Progress episode rows show the full air date (no ellipsis); blue bar = not aired yet, not a queue
- When Trakt progress already counts an episode as aired, Progress trusts that over a still-future `first_aired` timestamp
- Alerts: **Hide read** filter (default on, remembered) to cut clutter

## 2026-08-10 — Set lists checkboxes match membership only

- After **Remove from all lists**, reopening Set lists stays empty (Auto-select defaults are only via **Apply my defaults**, not re-applied on open)

## 2026-08-10 — Set lists dialog clarifies membership

- Renamed **Add to lists…** to **Set lists…** (add, update, and clear)
- Checkboxes show **actual membership** when already on a list; Auto-select defaults only for first-time add
- Dialog adds status line, **Apply my defaults**, and **Remove from all lists**

## 2026-08-10 — My Shows/Movies are list-scoped only

- **Watched / Both / Unwatched** are status filters inside the selected **Lists…** — watch history alone no longer puts a title on My shows/movies

## 2026-08-10 — Found on chips link to services

- **Found on** and **Plays on your services** chips open the service in a new tab (title search for Netflix/Prime/etc.)
- Custom services support a **Search template** in Preferences (`<title>` placeholder, e.g. `https://toflx.com/search?q=<title>`)

## 2026-08-10 — Episode ratings + Trakt reviews

- Progress panel: each episode has **Watch** plus **Rate / Review** (dialog with rating, review text, optional mark-watched — one Save)
- Dialog **lazy-loads** your existing Trakt rating + comment for that episode (and updates the comment in place when you already have one)
- Progress list load does not fetch all episode ratings up front
- Movie/show **title detail** only: **Write review…** posts/updates a Trakt comment with optional spoiler flag (min. 5 words)

## 2026-08-09 — Global loading overlay during refresh and navigation

- A full-page **loading overlay** with a spinner now covers the screen whenever a server action is in progress or a page is leaving
- Applies to **Refresh from Trakt**, **Load older Trakt page**, all `[data-action]` buttons (watchlist, watched, pin, favorite, review markers, etc.), form submissions, and normal page navigation
- The overlay dims the page and blocks further clicks, preventing accidental double-actions while Trakt calls are in flight
- Disabled buttons are now visually muted so it’s obvious a click was already registered

## 2026-08-07 — Admin scheduler controls

- New **Admin → Scheduler** page lets admins change background sync schedules without editing `.env` or restarting the server
- Catalog sync and media alerts can each run on an **interval** (every N minutes/hours) or **daily at a specific time** (e.g. `08:00` and `20:00`)
- Jobs can be individually enabled/disabled from the UI; saved settings apply immediately to the running scheduler
- The first interval-based media alerts run after boot still respects the `ALERTS_STARTUP_DELAY_SECONDS` delay; cron schedules and later UI changes are unaffected
- Settings are stored in the new `scheduler_config` table; env values are only used as defaults on the first app start
- Manual **Run alert check now** and **Reset to defaults** buttons are on the same page

## 2026-08-07 — My Shows renders from cache only (instant pages)

- My Shows/Movies pages no longer call Trakt for episode/progress data — the **Newest aired** view used to fire 10+ per-show API calls *while rendering*, taking 1–3 minutes whenever progress or last-aired data was stale. Both the newest-aired branch and the list view's per-page progress fill are gone
- The periodic media job (every `ALERTS_INTERVAL_HOURS`, default 6h) now maintains that cache: last-aired dates are derived for free from the My-calendar rows (window widened from 4 days to **33 days back / 33 days ahead** — same job, 2 calls instead of 1), list-only shows the calendar never covers get a sequential per-show seed, and progress refreshes for every show not known finished
- Throttle-aware: if the calendar fetch gets a 429, the whole per-show phase is skipped for that run; a 429 mid-seed stops the loop immediately. Nothing blocks a page either way
- Shows added on trakt.tv get seeded when the membership sync discovers them (bounded to a few per page load — a big list import can't slow a request; the job finishes the rest)
- **Refresh from Trakt** on My pages now queues a one-off background cycle (alerts + cache) instead of doing it inline; flash tells you to check back in a minute
- Show cards now append the **next episode's air date** (`Next: S02E01 — title · 2026-08-12`) from the cached calendar, and unwatched shows with an upcoming premiere get a Next line even without progress data

## 2026-08-07 — Alert runs back off under Trakt rate limits

- A 429 on the bulk calendar call no longer triggers per-show episode scans for every list-only show — that turned one throttle response into ~15 extra doomed calls. The run now skips fallbacks when throttled and catches up on the next run (the 3-day grace window means no episode is missed)
- A 429 mid-fallback stops the remaining per-show scans immediately
- Alert runs fetch only the shows calendar; the movies calendar was fetched on every run but never used by alerts

## 2026-08-07 — Fix duplicate show alerts (release + episode)

- Every new episode used to fire **two** alerts: "New episode" and "Released". Root cause: calendar sync stamped the *episode's* air date onto the show's `released_at`, and the date-keyed release payload then re-fired per episode. Show rows now only ever take their real premiere date (item-level episode dates ignored; `released_at` never moves later — existing polluted rows self-heal on the next sync)
- Shows no longer get release-day alerts at all: the S01E01 episode alert already announces a premiere, and full-season drops get the season alert. Movies keep **release-day** and **new-streaming** alerts unchanged
- Alerts page fallback button renamed **Open → View**; Preferences label clarified to "Movie release date"

## 2026-08-07 — Alerts page redesign

- Alert cards now show the poster, a linked title, a colored type tag (New episode / Season out / Released / Now streaming), and the episode line `S#E# — episode title · aired date`
- Streaming providers render as live tags (teal = on your services) instead of being baked into the message text; notifications now store `media_type`/`trakt_id` (auto-migrated) to power this
- Episode/season alerts get a **Progress** button that opens the progress side panel in place (previously "Open" navigated away to the full progress page); **Details** links to the title page

## 2026-08-07 — Episode alerts actually fire

- The alerts job was interval-only (every 12h) with no startup run, so frequent restarts meant it never ran; it now runs once ~2 minutes after boot, then every `ALERTS_INTERVAL_HOURS` (default 6h)
- Episode detection is **calendar-driven**: one bulk `/calendars/my` call per run covers every watchlisted or in-progress show for the whole 3-day grace window — no per-show scan queue, no rotation; newly added shows alert on the very next run
- List-only shows the calendar cannot cover (never watched, not watchlisted) fall back to a per-show Trakt fetch; suspected full-season drops confirm with a single extra call
- First-ever scan of a show now still alerts episodes/seasons aired within the 3-day grace window instead of swallowing them into the baseline
- Fixed Newest-aired refresh crashing with `'NoneType' object has no attribute 'id'` (login proxy was read inside worker threads)

## 2026-08-07 — Pin fix in Newest aired view

- **Pinned** titles sort at the top again in the My movies/shows **Newest aired** view; the mode used to ignore pins and sort purely by aired/release date

## 2026-08-07 — Latest movies/shows: hide list titles + stale-sort fix

- Latest movies/shows now default to **Hide list titles** (titles already on personal Trakt lists are hidden)
- Toggle **Show list titles** in the toolbar to see them again; choice is remembered per view
- Fixed `trakt_listed_at` sort key so catalog updates use the real Trakt `updated_at` instead of getting stuck on future release dates
- One-time startup migration repairs existing rows whose `trakt_listed_at` was set to a future release date

## 2026-08-06 — My Shows/Movies: Newest aired view

- New **Newest aired** view (beside List / Weekly / Daily / Monthly)
- Shows are sorted by the air date of their most recently aired episode (newest first)
- Movies are sorted by release date
- Titles whose latest episode / release is in the future are hidden
- Per-episode data is fetched from Trakt once and cached in `user_media_state.last_episode_aired_at`

## 2026-08-06 — Personal-list tags on all title cards

- Detail page, Latest, Search, and Recommendations now show personal-list tags (not just `Watchlist`)
- My Shows/Movies already showed personal-list tags; this fills the gap everywhere else
- Tag name comes from cached Trakt personal list names; missing list names default to "List"

## 2026-08-06 — My movies/shows calendar view

- **View: List / Weekly / Daily / Monthly** pills on My movies and My shows — Trakt-style calendar of episode air dates (shows) and movie releases from `/calendars/my`, filtered to the current Lists… / Watched selection
- Entries click through to the title detail page; calendar mode is remembered per view
- Calendar entries cached in `user_calendar_events`; failed Trakt fetches never blank the calendar

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
