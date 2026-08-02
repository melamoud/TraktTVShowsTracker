# Architecture

## Stack

| Layer | Choice |
|--------|--------|
| Web framework | Flask + Jinja templates |
| Auth | Trakt OAuth2 + Flask-Login sessions |
| DB | SQLite via Flask-SQLAlchemy (`instance/trakttv.db`) |
| CSRF | Flask-WTF |
| Background jobs | APScheduler |
| Streaming availability | Local assignment + TMDB Watch Providers (`US`) |
| TLS | `run.py` HTTPS with `cert.pem` / `key.pem` |

Patterns intentionally mirror `D:\dev\AudioBooksReview` (config, security headers, help docs, run/stop scripts, admin split).

## Route modules

- `routes/auth_routes.py` — Login with Trakt, callback, logout
- `routes/catalog_routes.py` — Home, latest movies/shows, detail, Trakt actions, markers
- `routes/user_routes.py` — Preferences, my lists, series progress, notifications, user help
- `routes/admin_routes.py` — Users, streaming defaults/approvals, admin help

## Data ownership

**Trakt (source of truth)**  
Watchlist, watched history, episode progress, identity.

**Local SQLite**  
Streaming services owned, found-on labels, genres/keywords, review markers, release watches, notifications, admin flags, encrypted Trakt tokens, cached catalog/providers.

## Admin bootstrap

1. Set `ADMIN_TRAKT_USERNAMES=your_slug` in `.env`
2. That Trakt user becomes admin on first login
3. After an admin exists, env promotion is ignored unless `ADMIN_ALLOW_ENV_PROMOTE=1`
4. Admins can promote/demote others in UI; last admin cannot be removed

## Catalog “Latest” = Trakt DB activity

Product intent: browse what was **added/changed in Trakt’s database** (not theatrical release calendars).

**Source:** `/movies/updates` and `/shows/updates`, rows tagged `feed_source=trakt_db_updates`, ordered by Trakt `updated_at` (stored as `trakt_listed_at`).

**Honest limits:** Trakt has no public `created_at` / “first inserted” field — first inserts and later metadata edits share this feed. Window is ~30 days. Watched titles are hidden by default to cut noise. Review markers use this Trakt DB timeline.

## Security

- HttpOnly / Secure / SameSite session cookies
- CSRF on unsafe methods
- Trakt tokens encrypted at rest (Fernet derived from `SECRET_KEY`)
- Disabled users cannot log in; sessions can be revoked (clears local tokens)
- Admin actions never mutate another user’s Trakt account
