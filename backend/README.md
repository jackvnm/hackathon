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
and workflow logic live in `app/services/`. Review uses shared backend eligibility rules; planning follows later.

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

## Dispatcher review

`GET /api/issues` returns a JSON array of public reports, newest ID first.
`?crew=roads` filters by assigned crew; the same identifiers as assignment
are accepted, including `manual_triage`. Empty results return `[]`.

`PATCH /api/issues/{id}` accepts any subset of `crew`, `task_type`,
`estimated_minutes`, `location`, and `review_state`; it returns the full
public report. Unknown fields are rejected. Duration may be null when
unknown; otherwise it must be a positive integer. Other controls cannot
be null. A location correction supplies all three fields: `lat`, `lng`,
`confirmed`. Clearing location uses null coordinates and `confirmed=false`.
Changing coordinates records `map_pin`; confirmation alone preserves source.

Any actual crew, task, duration or location change invalidates approval.
Changing task type also clears its old estimate unless the request supplies
a new duration. To explicitly approve the changed task, send
`review_state=approved` in that same request. A rejected approval rolls back
the entire PATCH. A no-op edit preserves approval.

Approval validates the complete resulting task: active, supported crew/task,
confirmed valid coordinates, positive known duration, and compatible
capabilities. Inspection uses its own crew inspection capability rather than
repair requirements and requires its own estimate. Model category/capability
conflicts cannot be overridden simply by approving an incompatible crew.
Reports with failed analysis can be explicitly assigned and approved by a
human. Analysis and source status remain separate from review.

`routable` uses `app/eligibility.py:task_blockers`, also intended for the
scheduler. It additionally requires approval and, when provided, matching
selected crew. Inactive reports and closed historical records are excluded;
only explicitly active synthetic copies can schedule from closed sources.
The ORM defaults new rows to inactive; submission explicitly sets active.
No schema migration is needed and existing records are preserved.

```sh
curl --fail-with-body 'http://127.0.0.1:8000/api/issues?crew=roads'

# Replace 1 with the ID returned by submission.
curl --fail-with-body -X PATCH http://127.0.0.1:8000/api/issues/1 \
  -H 'Content-Type: application/json' \
  -d '{"crew":"roads","task_type":"repair","estimated_minutes":45,"location":{"lat":53.34,"lng":-6.26,"confirmed":true},"review_state":"approved"}'
```

Missing reports return 404. Invalid input returns 422 in FastAPI's `detail`;
business validation uses `{"field":"estimated_minutes","message":"Duration
must be positive to approve"}` inside `detail`, while request-shape errors use
FastAPI's standard validation array. Database failures return 503 with an
explicit retrieval or update failure message. Public responses exclude email
and internal photo paths.

Next milestone: labelled synthetic demo data and OSRM daily planning.
`POST /api/plan` is **not implemented yet**. Its agreed future request is:

```sh
# Run only after the planning milestone is implemented.
curl --fail-with-body -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' -d '{"crew":"roads"}'
```

Rehearse now: submit a photo, list it, correct/approve it with an explicit
estimate and confirmed pin, verify `routable=true`, then change duration and
verify approval resets. Generating an itinerary still awaits planning. Live
OpenAI classification requires credentials; tests use synthetic images and
mock model responses. Frontend browser verification remains outstanding.

Official references: [image inputs](https://developers.openai.com/api/docs/guides/images-vision)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Verification

```sh
uv run python -m unittest discover -s tests -v
```

Tests generate clearly synthetic photos in temporary directories and never
save reporter data or photo fixtures into the repository.
