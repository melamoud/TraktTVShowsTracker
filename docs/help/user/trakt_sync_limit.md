# Trakt DB updates limit (Latest feed)

## What Latest uses

`/movies/updates` and `/shows/updates` — titles recently **added or modified in Trakt’s database**.

## Limits

1. **~30-day window** — older start dates return an empty list. That is Trakt’s hard API limit.  
2. **No `created_at`** — Trakt does not publish “first inserted” separately from `updated_at`, so first inserts and later metadata edits share one feed.  
3. **Local DB** — anything we already synced stays available forever in this app.  
4. **Lazy paging** — first load / Refresh takes **one newest** Trakt page only; older pages load when you page back. Pulling the entire ~30-day window in one request rate-limits Trakt (HTTP 429).

Website pages like `trakt.tv/movies/added` exist in the Trakt web UI, but there is **no documented public API** equivalent we can call cleanly; Latest uses the official updates API instead.

Keep sync running regularly so your local catch-up history keeps growing.
