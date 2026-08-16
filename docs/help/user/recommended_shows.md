# Recommended shows

Personalized series picks from Trakt — the same Recommendations feed as on Trakt.tv.

## Source

Uses Trakt’s `/recommendations/shows` API (requires your Trakt login).

## Categories

Genre tabs come from **your Preferences genres** (plus **All**). Selecting a genre filters Trakt recommendations to that category.

## Filters

- **Hide wishlist** (default on)  
- **Hide watched** (default on)  
- **On my services** — only titles available on services you marked in Preferences  
- **Matches only** — purple preference matches  
- **10 / 50 / 100** per page  
- **Search titles in this list…** — filter current results by title  
- **More filters** — year range and genres (any selected)

## Highlights

- Purple genre/keyword match tags  
- **Plays on your services** teal callout when TMDB lists one of your services  
- **Set lists…** — Wishlist + personal Trakt lists (multi-select)  
- **Rate…** / **Favorite** — same Trakt rating and favorites as on trakt.tv  
- **Hide recommendation** — Trakt “Not interested”; drops it from future picks  

See also Help → Recommended movies for the shared workflow (the list is cached for the admin Trakt read-cache TTL; watched/list tags come from the same local title state as My / Latest).
