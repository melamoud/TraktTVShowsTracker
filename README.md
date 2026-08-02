# TraktTV Shows Tracker

Web app to discover newly listed movies/shows on Trakt, match them to your streaming preferences, sync watchlist/watched/progress with TraktTV, and keep local extras (found-on services, review markers, release alerts).

Built with **Python Flask + SQLite**, following the same operational patterns as AudioBooksReview (HTTPS runner, CSRF, help docs, admin/user route split).

## Quick start

1. Copy `.env.example` → `.env` and set Trakt API keys + `ADMIN_TRAKT_USERNAMES`
2. Double-click or run `run.bat`
3. Open `https://localhost:8300` and **Login with TraktTV**
4. Stop with `stop.bat`

Details: [docs/SETUP.md](docs/SETUP.md)

## Documentation

- [Original prompt](docs/ORIGINAL_PROMPT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Setup](docs/SETUP.md)
- [Deployment](docs/DEPLOYMENT.md) (`tvtracker.melamoud.com`)
- [Changes](docs/CHANGES.md)
- In-app **Help** menu (`docs/help/user` and `docs/help/admin`)

## Main features

- Login with Trakt (friends/family each use their own Trakt account)
- Latest movies & shows (10/50/100), preference highlights, watchlist/watched, review marker
- Read-only **Streaming:** (TMDB/JustWatch) vs local multi-select **Found on…**
- Preferences: streaming services (defaults + custom + admin approval), genres/keywords
- My movies / My shows (default Wishlist); series progress with Trakt write-back
- In-app release alerts when a title appears on streaming
- Admin: users, services, manual release check, help

## Tests

```bat
.venv\Scripts\pytest.exe -q
```

## Git remote

Local git is initialized in this folder. Mirror AudioBooksReview by creating a GitHub repo under `melamoud` (install [GitHub CLI](https://cli.github.com/) then):

```bat
gh repo create melamoud/TraktTVShowsTracker --private --source=. --remote=origin --push
```
