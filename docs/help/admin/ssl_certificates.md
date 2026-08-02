# SSL certificates

Local:

```bat
python generate_cert.py
```

Creates `cert.pem` / `key.pem` (gitignored). Browsers will warn — expected.

Production: terminate TLS at Cloudflare / Nginx / Caddy for `tvtracker.melamoud.com`, or point `SSL_CERT_FILE` / `SSL_KEY_FILE` at a real certificate pair.
