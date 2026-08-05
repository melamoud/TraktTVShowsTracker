# Alerts

In-app messages under **Alerts** in the nav (badge = unread). They cover titles on your **Wishlist** and **personal lists**.

This is separate from **Streaming vs Found on** (where a title plays / where you found it).

## What you can get

| Alert | Meaning |
|-------|---------|
| **Release date** | A listed title’s release day arrives |
| **Added to a streaming service** | Any service starts carrying that title (one alert per new service) |
| **New episode or season** | An episode aired; if a full season drops the same day, one season alert instead |
| **New user signed up** | Admins only — first login of a new account |

## When they stop

- Movie marked watched  
- Show fully watched  
- Title no longer on Wishlist or any personal list  

## Turning types off

**Preferences → Alerts** — uncheck any type. Defaults are on.

## How they arrive

Written in the background (about every `PROVIDER_SYNC_INTERVAL_HOURS`). You see them next login or page refresh. Admins can run **Run alert check now** from the Admin dashboard.

Streaming-service alerts need a free `TMDB_API_KEY` in `.env`.
