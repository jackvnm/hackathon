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

Persistence uses SQLAlchemy ORM with SQLite. `app/main.py` configures the app,
middleware and lifecycle; endpoints live in `app/routers/`. Classification
and workflow logic live in `app/services/`. Review and planning follow later.

## Submission

`POST /api/issues` accepts multipart fields `photo`, `description`, `email`,
optional `address`, optional paired `lat`/`lng`, and `location_confirmed`
(defaults to false). Coordinates alone do not imply confirmation. An address
alone is saved as unlocated. Photos must be valid JPEG, PNG or WebP, at most
10 MiB and 20 million pixels. Original bytes are stored under generated names.

GPS is extracted from the original photo before any transformations. Without
a pin, valid photo GPS becomes the canonical location. A differing pin overrides
GPS; confirming the same coordinates retains `photo_gps` as the source. Both
GPS and pins require explicit `location_confirmed=true` to confirm them.
Missing or malformed GPS is unlocated unless a pin is supplied. Frontend EXIF
inspection can control its form, but backend extraction remains authoritative.

```sh
curl --fail-with-body http://127.0.0.1:8000/api/issues \
  -F 'photo=@/absolute/path/to/demo-photo.jpg' \
  -F 'description=Visible pothole near the kerb' \
  -F 'email=demo@example.com' \
  -F 'lat=53.34' -F 'lng=-6.26' -F 'location_confirmed=true'
```

Success is HTTP 201 with a reference, relative `photo_url`, analysis state
and `needs_review`. It does not imply approval or routing eligibility. Email
is stored privately and excluded from the response. Photos can be retrieved
using the returned URL. Storage failure is HTTP 503, explicitly saying the
submission was not saved. Invalid fields/images return 422; oversized files
return 413. Failures return FastAPI's `detail` field.

## OpenAI classification

Set `OPENAI_API_KEY` server-side (for example in an ignored `backend/.env`)
and run uvicorn with `--env-file .env`. `OPENAI_MODEL` defaults to
`gpt-4.1-mini` and can be changed to a model supporting image inputs and
structured outputs. The original photo and description are sent together
through `client.responses.parse`, with Pydantic validation. Reporter email
is never included. The report and original photo commit before analysis.

A missing key, API failure, refusal or invalid result returns the saved report
with `analysis_state=failed`, `analysis_error`, and `review_state=needs_review`.
If saving the analysis result fails, the original remains saved and pending,
with an explicit `analysis_error`. Classification never approves a task.

Backend category mappings assign roads to repair, cleanup and graffiti to
removal, and lighting, arborist and drainage to inspection/review. Unlisted
categories require manual triage. Unknown durations remain null. Repair
estimates are never reused when a specialist task is changed to inspection.
Mappings and crew capabilities are configured in `app/assignments.py`.

Available now: health, multipart submission and original-photo retrieval.
`GET /api/issues`, dispatcher PATCH and `POST /api/plan` are subsequent
milestones. Frontend mocks for those endpoints should continue matching
AGENTS.md until they are implemented.

Official references: [image inputs](https://developers.openai.com/api/docs/guides/images-vision)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Verification

```sh
uv run python -m unittest discover -s tests -v
```

Tests generate clearly synthetic photos in temporary directories and never
save reporter data or photo fixtures into the repository.
