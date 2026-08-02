# Security

- HTTPS via `run.py` (self-signed locally; real certs in production)
- Session cookies: HttpOnly, Secure, SameSite=Lax
- CSRF on POST/AJAX
- Trakt tokens encrypted at rest
- Disabled users cannot authenticate
- Admin tools never write to another user’s Trakt account
