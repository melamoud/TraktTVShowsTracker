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
- Hidden genres from Preferences are always dropped (even with Matches only off)  
- **10 / 50 / 100** per page  
- **Filter this page…** — filter the current recommendation results by title (not remembered)
- **More filters** — year range, actor (jumps to Search), and genres (any selected); remembered for this page
- **Upcoming / Theater window / Streaming** — same availability chips/filters as My / Latest

The recommendation list is cached locally for the admin **Trakt read cache** TTL (default 2 hours). Wishlist/watched **tags** always come from the same local title state as My / Latest, so a watch on another screen shows up here immediately.

## Highlights

- **Purple** tags — which of your genres/keywords matched (same as Latest)  
- **Plays on your services** — teal highlight for services you own that list the title (needs `TMDB_API_KEY`)  
- **Set lists…** — multi-select Wishlist + your Trakt personal lists (hide unused lists under Preferences)  
- **Rate…** / **Favorite** — same Trakt rating and favorites as on trakt.tv  
- **Hide recommendation** — same as Trakt.tv “Not interested”; removes it from future Trakt recommendations  

Set services and genres under Preferences for the best experience.
