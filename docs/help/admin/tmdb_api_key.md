# TMDB API key (free)

Streaming lines and release alerts need a **free** TMDB API key. Trakt’s site shows the same JustWatch-style data, but Trakt does **not** expose it in their API.

## Get a key

1. Create/sign in at https://www.themoviedb.org/  
2. Open https://www.themoviedb.org/settings/api  
3. Request an API key (choose **Developer** / personal use)  
4. Copy the **API Key (v3 auth)**  

## Configure

In `.env`:

```
TMDB_API_KEY=your_key_here
STREAMING_REGION=US
```

Restart the server (`stop.bat` then `run.bat`).

## Verify

- Latest movie tiles show **Streaming:** services (when TMDB has data)  
- Admin dashboard shows TMDB key: **configured**  
- Admin → **Run release check now** after you’ve used **Alert when streaming** on a title  
