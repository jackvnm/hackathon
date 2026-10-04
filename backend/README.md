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
and workflow logic live in `app/services/`. Review and planning use the same backend eligibility rules.

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
Missing or malformed GPS is unlocated unless a pin is supplied. The reporting form first calls `POST /api/photos/metadata` with the original
photo. This read-only multipart endpoint returns `{gps_found, location}` using
the same JPEG/PNG/WebP validation and EXIF extraction as submission. It does not
save a report/photo or call the model. Coordinates are returned unconfirmed.
The form hides address entry while checking or when valid GPS is found, offers
confirmation of the photo pin, and sends `location_confirmed` on submission.
A failed metadata request is shown with retry rather than treated as missing
GPS. Final submission independently extracts and validates metadata again.

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
Imported reports allow null description, email and photo fields. On startup, an
older SQLite table with required fields is backed up in the data directory as
`issues.pre-nullable-<timestamp>-<random>.sqlite3`, then rebuilt transactionally
with existing records preserved. Keep that backup until the demo is verified.

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

## Demo data

From `backend/`, seed 15 prepared scenarios into the configured database:

```sh
uv run python -m app.seed
# Optional alternative CSV source:
uv run python -m app.seed /absolute/path/to/dcccustomerservicerequestsp20130409-0956.csv
```

The default source is the repository's `dcccustomerservicerequestsp20130409-0956.csv`.
Seeding is idempotent through `DEMO-*` references and does not overwrite dispatcher
edits. It uses `CIVIC_DATA_DIR`, so use the same directory for seeding and uvicorn.
Seeded tasks are clearly synthetic; their estimates are invented demo values,
not measured historical repair times. Scenarios cover roads, cleanup, graffiti,
specialist review, approval omissions, missing locations/durations, incompatible
capabilities, oversized work, and an inactive historical report.

All nine source columns are preserved in `original`. Original `STATUS` remains
separate from review. Historical rows remain inactive; explicitly labelled
synthetic copies can be active even when their source was closed. Imported
reports have no fabricated reporter emails or photos: `description` and
`photo_url` may be null. Retrieving a photo from a report without one returns 404.

Coordinates are detected per row: ITM (EPSG:2157) and older Irish Grid
(EPSG:29902) both occur. Missing, placeholder `999999`, or unsupported values
remain unlocated; original X/Y values are preserved. Recognised coordinates are
converted to WGS84 using pyproj with a Dublin bounds check. Landmark samples
from both systems were checked against map locations before conversion. The
seed command processes prepared scenarios rather than importing the entire CSV.
The source was rechecked: 31,417 records, nine columns, 43 categories; detection
yielded 20,561 ITM, 10,703 Irish Grid and 153 unlocated rows. Converted samples
on Westmoreland Street, St Stephen’s Green and Dame Street were verified on
OpenStreetMap street tiles.

## Daily planning

`POST /api/plan` accepts `{"crew":"roads"}` (one crew instance). It returns
`label: "Suggested feasible route"`, `depot`, ordered `stops`, `lunch`,
`depot_return`, `totals`, and `omitted`. Each stop contains `order`, `report_id`,
`lat`, `lng`, `arrive`, `complete`, `travel_minutes`, and `task_minutes`.
`lunch` contains coordinates plus `start`/`end`; totals contain
`travel_minutes` (including return) and `task_minutes`. Times are Dublin local
`HH:MM` strings for the demo day; they are not UTC timestamps.

```sh
curl --fail-with-body -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' -d '{"crew":"roads"}'
```

Defaults: depot `53.34,-6.26`, OSRM `https://router.project-osrm.org`, timeout
15 seconds. Override with `CIVIC_DEPOT_LAT`, `CIVIC_DEPOT_LNG`,
`CIVIC_OSRM_URL`, and `CIVIC_OSRM_TIMEOUT_SECONDS`.

Planning selects approved, confirmed, known-duration, active and compatible
work through the shared eligibility function. It greedily chooses the feasible
candidate with lowest travel-plus-task minutes. Shift is 08:00–16:00, lunch is
12:00–13:00 at the current location, and driving plus tasks (including depot
return) cannot exceed 420 minutes. Travel and tasks are indivisible: if an
activity would overlap lunch, its start is deferred to 13:00. Waiting, lunch,
and depot-return feasibility are accounted for after every candidate. This is
a suggested feasible route, not a globally optimal solution.

Omitted reports include an actionable message and reason such as `unapproved`,
`unlocated`, `unknown_duration`, `incompatible_crew`, `manual_triage`, `inactive`,
or `oversized`. OSRM failure returns HTTP 503 with a clear planning error;
there is no straight-line fallback. With no eligible jobs, an empty plan is
returned without contacting OSRM.

## Frontend integration and rehearsal

The frontend should use the existing endpoints directly: GET returns an array,
POST/PATCH return a full report, and plan stops refer to integer report IDs.
Render null `photo_url`/`description` for dataset reports without requiring a
photo. Display backend `routable`, itinerary times, totals and omission messages;
keep scheduling and eligibility on the backend. Existing plan response fields
match the dispatcher itinerary contract. Frontend browser verification is still
a separate integration step owned by the frontend developer.

1. Run `uv sync --locked`, then seed with `uv run python -m app.seed`.
2. Set `OPENAI_API_KEY` in an ignored `.env` for real photo classification;
   start `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env`
   (omit `--env-file .env` if using environment variables).
3. Submit a real issue photo using the multipart curl example above, with a
   confirmed pin. Save the returned ID/reference. HTTP 201 means saved even
   when analysis failed; never present failure as a lost submission.
4. Retrieve `/api/issues`, then correct and explicitly approve the saved ID
   using PATCH with its task, estimate, crew and confirmed coordinates.
5. Generate `/api/plan` for that crew. Check the saved ID among stops, lunch
   at 12:00–13:00, return by 16:00, and omissions for unsuitable demo reports.
6. Change the saved task duration without sending approval; verify
   `review_state=needs_review` and `routable=false`, then explicitly reapprove.
7. Repeat in the React dispatcher against the live API, including cleanup and
   graffiti. No browser check or real OpenAI call is implied by seeded data.

Planning requires network access to OSRM. Live OpenAI classification requires
credentials. Local automated tests use synthetic images, mock model responses
and controlled travel times. Verification: all 50 backend tests passed. A temporary uvicorn + curl rehearsal
used the real OSRM service to generate roads, cleanup and graffiti plans,
including a newly uploaded synthetic photo after manual correction/approval.
Seeding inserted 15 records and the second run inserted zero. Real model
classification remains unverified; browser control was unavailable.

Official references: [image inputs](https://developers.openai.com/api/docs/guides/images-vision)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Verification

```sh
uv run python -m unittest discover -s tests -v
```

Tests generate clearly synthetic photos in temporary directories and never
save reporter data or photo fixtures into the repository.
