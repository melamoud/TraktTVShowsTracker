# System configuration

Important `.env` keys:

- `TRAKT_CLIENT_ID` / `TRAKT_CLIENT_SECRET` / `TRAKT_REDIRECT_URI`
- `TMDB_API_KEY` / `STREAMING_REGION=US`
- `ADMIN_TRAKT_USERNAMES` — first matching login becomes admin
- `ADMIN_ALLOW_ENV_PROMOTE=0` — keep at 0 so nobody else becomes admin just by editing env later
- `PORT=8300`, `PUBLIC_HOST=tvtracker.melamoud.com`

See `docs/SETUP.md` and `config.py`.
