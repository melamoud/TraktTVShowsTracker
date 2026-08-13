# Testing

```bat
.venv\Scripts\pytest.exe -q
```

Default tests use an isolated SQLite DB and mock Trakt. Optional live credentials belong in `.env.test` (never commit).

`tests/test_mobile_api.py` covers the Android `/api/v1` session + JSON endpoints. Restart Flask after pulling those routes or the phone app gets HTTP 404.
