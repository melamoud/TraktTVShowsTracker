# Recommended movies

Personalized movie picks from Trakt — the same Recommendations feed as on Trakt.tv.

## Source

Uses Trakt’s `/recommendations/movies` API (requires your Trakt login). Results are ordered by Trakt’s recommendation ranking.

## Categories

Genre tabs come from **your Preferences genres** (plus **All**). Selecting a genre asks Trakt for recommendations filtered to that genre slug (same idea as Trakt.tv category browsing).

## Filters

- **Hide wishlist** (default on) — drop titles already on your Trakt watchlist  
- **Hide watched** (default on) — drop titles you’ve already watched  
- **On my services** — keep only titles TMDB lists on a streaming service you marked in Preferences  
- **Matches only** — purple genre/keyword preference matches only  
- **10 / 50 / 100** per page  
- **Search titles in this list…** — filter the current recommendation results by title/year (not remembered)
- **Upcoming / Theater window / Streaming** — same availability chips/filters as My / Latest

The recommendation list itself is fetched live from Trakt each visit. Wishlist/watched tags used for hide filters also auto-refresh when Trakt activity timestamps advance.

## Highlights

- **Purple** tags — which of your genres/keywords matched (same as Latest)  
- **Plays on your services** — teal highlight for services you own that list the title (needs `TMDB_API_KEY`)  
- **Add to lists…** — multi-select Wishlist + your Trakt personal lists (hide unused lists under Preferences)  
- **Hide recommendation** — same as Trakt.tv “Not interested”; removes it from future Trakt recommendations  

Set services and genres under Preferences for the best experience.
