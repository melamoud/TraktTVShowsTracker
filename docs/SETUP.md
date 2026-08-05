# Setup

## Prerequisites

- Python 3.11+
- A free [Trakt.tv](https://trakt.tv) account (Google login is fine on Trakt’s side)
- A **free** [TMDB](https://www.themoviedb.org/settings/api) API key for Streaming lines + streaming alerts (see Admin help → TMDB API key)

## 1. Create a Trakt API application

End users only need a Trakt account. **You** (the operator) also need an API app so this site can do OAuth:

1. Sign in at https://trakt.tv
2. Open https://trakt.tv/oauth/applications
3. Create a new application, e.g. **TraktTV Shows Tracker**
4. Redirect URI (local): `https://localhost:8300/auth/callback`
5. Later for production: `https://tvtracker.melamoud.com/auth/callback`
6. Copy Client ID and Client Secret into `.env`

## 2. Install and configure

```bat
cd D:\dev\TraktTVShowsTracker
copy .env.example .env
:: edit .env — set TRAKT_*, TMDB_API_KEY, ADMIN_TRAKT_USERNAMES
run.bat
```

`run.bat` creates `.venv`, installs requirements, generates a self-signed cert if needed, and starts HTTPS on port **8300**.

Stop with:

```bat
stop.bat
```

Or PowerShell:

```powershell
.\scripts\start-backend.ps1
.\scripts\stop-backend.ps1
```

## 3. First admin login

1. Set `ADMIN_TRAKT_USERNAMES` to your Trakt username
2. Open `https://localhost:8300` (accept the self-signed warning)
3. Click **Login with TraktTV**
4. You become admin on first successful login

## 4. Friends & family

They need their own Trakt accounts. They use the same **Login with TraktTV** button. No local passwords.

## 5. Production host

See [DEPLOYMENT.md](DEPLOYMENT.md) for Cloudflare / `tvtracker.melamoud.com` checklist.

Short version:

1. Point DNS at your host  
2. Prefer Cloudflare or Caddy TLS; update Trakt redirect URI  
3. Set `TRAKT_REDIRECT_URI`, `PUBLIC_HOST`, and free `TMDB_API_KEY`  

## 6. Test credentials

For automated live tests (optional), create a dedicated Trakt test user and put secrets in **`.env.test`** (gitignored):

```
TRAKT_CLIENT_ID=...
TRAKT_CLIENT_SECRET=...
TRAKT_TEST_USERNAME=...
# Live OAuth for CI is awkward; default tests mock Trakt.
```

Run unit/API tests (mocked):

```bat
.venv\Scripts\pytest.exe -q
```
