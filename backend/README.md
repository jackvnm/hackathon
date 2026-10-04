# Backend

Run commands from `backend/` using the existing uv project:

```sh
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health: `GET http://127.0.0.1:8000/api/health`. OpenAPI: `/docs`.
The React development origin `http://localhost:5173` is allowed by default.

Configuration is read from environment variables. See `.env.example`; if
using a local `.env`, add `--env-file .env` to the uvicorn command.
`CIVIC_DATA_DIR` defaults to `backend/data`; `CIVIC_CORS_ORIGINS` is a
comma-separated list. Credentials, local databases and uploads must not
be committed.

The storage milestone does not call OpenAI or implement review or planning.
