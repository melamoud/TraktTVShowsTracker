# Testing

```bat
.venv\Scripts\pytest.exe -q
```

Default tests use an isolated SQLite DB and mock Trakt. Optional live credentials belong in `.env.test` (never commit).
