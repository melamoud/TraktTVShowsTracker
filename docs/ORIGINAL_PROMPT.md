# Original product prompt

This document preserves the initial product request used to design TraktTV Shows Tracker.

## Goal

Build a web service to help find new shows and movies to watch, mark them against a TraktTV account, track watched state, and see whether titles are found in the user’s streaming services.

The user currently uses the Showly Android app (backed by TraktTV) but is missing important functionality. This project is a web alternative for those gaps first; a mobile app may come later.

## High-level screens

- User management with “Login with TraktTV”
- Latest movies added to TraktTV (10/50/100 per page), preference highlights, list/watched highlights, mark watched / wishlist, review marker
- Latest shows added to TraktTV (same behaviors)
- User preferences: streaming services (defaults + custom + admin approval), genres/keywords
- My movies / My shows (wishlist / watched / both); track series with unwatched episodes
- Series progress: dim watched seasons/episodes, jump to next episode, write back to Trakt
- Metadata: network/channel, dates, IMDb, trailers, other Trakt links
- Help menu for every functionality (user + admin)
- Admin is also a normal user with their own Trakt account
- Secure code, tests, README/docs, start/stop scripts, git support
- Split admin and user routes into different route files
- Short comments on functions/objects/APIs

## Decisions captured in follow-up

- Stack mirrors AudioBooksReview: Python Flask + SQLite (not Node)
- Watchlist = Trakt watchlist
- Watched/progress sync to Trakt; “found on” streaming assignment is local
- Streaming availability: manual assignment + TMDB Watch Providers (US)
- Release alerts in-app when a watched title appears on any streaming service
- Local first (`localhost:8300`), later `tvtracker.melamoud.com` (Cloudflare)
- Admin via `ADMIN_TRAKT_USERNAMES`, locked after first admin unless explicitly re-opened
- Git: local + GitHub remote (like AudioBooksReview / melamoud)
