# Streaming vs Found on

These are **two different things**:

## Streaming (read-only)

Shown on **Latest** tiles (and detail pages) as **Streaming:**.

- Comes from **TMDB / JustWatch** availability for your region (`STREAMING_REGION`, default US)
- Trakt’s website uses the same kind of data, but **does not expose it in the Trakt API**
- Requires a free `TMDB_API_KEY` in `.env`
- You cannot edit this list — it is informational only

## Found on (your choice)

Used on **My movies / My shows** (and detail).

- Local only — never written to Trakt
- Click **Found on…** and select **one or more** services (including your custom ones)
- Services that TMDB lists for the title are **highlighted** as a hint; you still choose what you actually use
- The tile shows only the services **you** saved
