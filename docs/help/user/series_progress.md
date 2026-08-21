# Series progress

Shows **aired** episodes for a series and which ones you’ve watched on Trakt.

**Progress** / **Series progress** on My shows, Search, and show detail opens a **side panel** over the current page (no navigation away). Mark episodes/seasons there; the panel refreshes in place from the local progress cache (the same object My cards and Alerts use). Closing it after changes reloads the underlying page so card counts update. The full `/shows/…/progress` URL still works for bookmarks. Trakt is re-fetched for that show only when the cache is older than the admin TTL, after an explicit refresh, or when a write could not be applied locally.

## Where watched marks come from

Episode **Watch / Watched** uses the same Trakt sync sources Showly and Kodi use:

1. `/sync/history/shows/{id}` — per-show watch history  
2. `/sync/watched/shows?extended=progress` — per-episode `plays` (required after Trakt’s 2026 API change; without `extended=progress` season/episode breakdown is omitted)  
3. `/shows/{id}/progress/watched` — `completed` / play counts when present  

If an episode is not in any of those, Trakt has **not** recorded a watch for this account — even if Showly’s local UI or a website checkmark looks filled. Showly can keep local checks that never uploaded ([Showly sync issues](https://github.com/trakt/showly/issues/579)).

## Episode list

- Header counts are **regular seasons only** (season 1+). Specials are listed separately at the bottom and do not make a show look like “0 watched” when you’ve finished season 1.  
- Title on one line; air date on the next (`Aired …` / `Airs … · Not aired yet`) so dates aren’t cut off  
- Future (not-yet-aired) episodes use a **blue left bar** — that means upcoming, not a queue  
- **Watch** / **Watched** — quick history toggle on the row  
- **Rate / Review** — opens a dialog that **loads your existing Trakt rating/review** (if any), then lets you set a 1–10 rating, edit the comment, and optionally mark watched in one save  
- **Next up** prefers the next unwatched regular-season episode, not a special; title and Watch sit side-by-side so long names stay readable  
- Expand **Episodes** under each season header to mark individual episodes  


## Actions

- **Watch** / next-up **Watch** — writes the episode to Trakt history (must succeed before the button flips). Trakt then **drops the show from Wishlist**; a personal list is what keeps it on My Shows ([Wishlist vs lists](wishlist))  
- **Watched** (click) — removes it from Trakt history  
- **Rate / Review** — dialog: rating menu, review text (optional spoiler), **Mark watched**, then **Save to Trakt**  
- **Mark season watched** — on each incomplete season row; marks all **aired** episodes in that season on Trakt (same as marking a season on Trakt.tv)  
- **Unwatch season** — on each complete season row; removes that season’s plays from Trakt history only  
- **Mark series watched** — next to the header counts; marks **all** aired episodes of the show on Trakt (every remaining season). Confirm carefully — this is not the same as marking one season. Local card % is refreshed from Progress counts afterward (the app does not invent a sticky 100%).  
- Counts at the top are `watched / aired` from history (+ progress plays when history lags)  

My shows auto-syncs watchlist/watched when Trakt activity advances; **Refresh from Trakt** forces a full pull. Neither writes episode history.

If the panel says Trakt is **rate-limiting**, wait a few seconds and click **Retry**. A sync that just ran can use up Trakt’s shared quota; the next try usually works once that settles.

If Trakt’s website shows a checkmark but this page still says **Watch**, Trakt has no history for that episode on this account. Click **Watch** here once — after a successful write the button becomes **Watched**.
