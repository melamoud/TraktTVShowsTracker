# Series progress

Shows **aired** episodes for a series and which ones you’ve watched on Trakt.

## Where watched marks come from

Episode **Watch / Watched** uses the same Trakt sync sources Showly and Kodi use:

1. `/sync/history/shows/{id}` — per-show watch history  
2. `/sync/watched/shows?extended=progress` — per-episode `plays` (required after Trakt’s 2026 API change; without `extended=progress` season/episode breakdown is omitted)  
3. `/shows/{id}/progress/watched` — `completed` / play counts when present  

If an episode is not in any of those, Trakt has **not** recorded a watch for this account — even if Showly’s local UI or a website checkmark looks filled. Showly can keep local checks that never uploaded ([Showly sync issues](https://github.com/trakt/showly/issues/579)).

## Episode list

- Header counts are **regular seasons only** (season 1+). Specials are listed separately at the bottom and do not make a show look like “0 watched” when you’ve finished season 1.  
- One line per episode: title, air date (`Aired …` / `Airs … · Not aired yet`), and the action button  
- Future episodes use a blue highlight  
- Buttons: **Watch** (not in history) vs **Watched** (in history; click to unwatch)  
- **Next up** prefers the next unwatched regular-season episode, not a special; title and Watch sit side-by-side so long names stay readable  
- Expand **Episodes** under each season header to mark individual episodes  


## Actions

- **Watch** / next-up **Watch** — writes the episode to Trakt history (must succeed before the button flips)  
- **Watched** (click) — removes it from Trakt history  
- **Mark season watched** — on each incomplete season row; marks all **aired** episodes in that season on Trakt (same as marking a season on Trakt.tv)  
- **Mark series watched** — next to the header counts; marks all aired episodes of the show  
- Counts at the top are `watched / aired` from history (+ progress plays when history lags)  

If Trakt’s website shows a checkmark but this page still says **Watch**, Trakt has no history for that episode on this account. Click **Watch** here once — after a successful write the button becomes **Watched**.
