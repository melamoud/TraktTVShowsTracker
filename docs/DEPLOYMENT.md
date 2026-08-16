# Deployment — tvtracker.melamoud.com

Local HTTPS on `https://localhost:8300` is the default. Production target: **tvtracker.melamoud.com**.

## Recommended shape

```
Internet → Cloudflare (DNS + TLS) → origin host:8300 (Flask HTTPS or HTTP behind proxy)
```

Prefer terminating TLS at Cloudflare (or nginx/Caddy) and running Flask with a real cert or plain HTTP on localhost behind the proxy.

## 1. DNS (Cloudflare)

1. Create an A/AAAA (or CNAME) record for `tvtracker.melamoud.com` pointing at your host  
2. Proxy through Cloudflare (orange cloud) if you want their certificate  

## 2. Trakt OAuth redirect

In https://trakt.tv/oauth/applications add:

`https://tvtracker.melamoud.com/auth/callback`

Keep the localhost redirect for local dev if Trakt allows multiple URIs; otherwise switch when you cut over.

## 3. Production `.env` on the host

```
DEBUG=0
HOST=0.0.0.0
PORT=8300
PUBLIC_HOST=tvtracker.melamoud.com
SESSION_COOKIE_SECURE=1
TRAKT_REDIRECT_URI=https://tvtracker.melamoud.com/auth/callback
ADMIN_TRAKT_USERNAMES=nirmelamoud
TMDB_API_KEY=...          # free from themoviedb.org
STREAMING_REGION=US
```

Use a strong `SECRET_KEY` (or let `.flask_secret_key` be generated once on the host and keep that file).

## 4. Run on the host

```bat
cd D:\dev\TraktTVShowsTracker
copy .env.example .env
:: edit .env
run.bat
```

`run.bat` starts HTTPS with the scheduler (catalog sync + release checks). Use `stop.bat` to stop (also clears stale listeners on port 8300).

### Windows service / Task Scheduler (optional)

Create a Task Scheduler task that runs at logon/startup:

`D:\dev\TraktTVShowsTracker\run.bat`

Or run under NSSM / WinSW as a service wrapping `.venv\Scripts\python.exe run.py`.

## 5. Reverse proxy sketch (Caddy)

If Cloudflare connects to your origin over HTTP on an internal port:

```
tvtracker.melamoud.com {
    reverse_proxy 127.0.0.1:8300
}
```

Then you may run Flask with `run.py --http` and `SESSION_COOKIE_SECURE=1` still set if the browser only sees HTTPS via Cloudflare.

## 6. Checklist before go-live

- [ ] Trakt redirect URI matches production  
- [ ] `PUBLIC_HOST` / `TRAKT_REDIRECT_URI` updated  
- [ ] `TMDB_API_KEY` set (Streaming + streaming alerts)  
- [ ] Admin can log in; friends/family can log in  
- [ ] Admin → **Run release check now** works after TMDB key  
- [ ] `stop.bat` / restart verified on the host  
- [ ] Backup `instance/trakttv.db` (double-click `push-db.bat` → private `TraktTVShowsTracker-db` repo) and `instance/poster_cache/` periodically  

## 7. What is not automated yet

- Cloudflare tunnel / full IIS binding scripts  
- Automated Let’s Encrypt renewals (use Cloudflare or Caddy)  

Those can be added once the host networking layout is fixed.
