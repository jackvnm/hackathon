"""Small repeatable synthetic scenarios derived from preserved source records."""
import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.assignments import CATEGORIES
from app.coordinates import csv_location
from app.database import Database, Issue
from app.eligibility import task_blockers
from app.models import Analysis


SOURCE_FIELDS = {
    "INCIDENT_NUMBER", "SR_CREATION_CHANNEL", "INCIDENT_ADDRESS", "STATUS",
    "GROUP_NAME", "NAME", "INCIDENT_DATE", "ATTRIBUTE5", "ATTRIBUTE6",
}

# Durations are invented demo estimates, never historical measurements.
SCENARIOS = [
    ("roads-1", "roads", 70, "approved"),
    ("roads-2", "roads", 80, "approved"),
    ("roads-3", "roads", 90, "approved"),
    ("roads-4", "roads", 75, "approved"),
    ("cleanup-1", "cleanup", 60, "approved"),
    ("cleanup-2", "cleanup", 100, "approved"),
    ("graffiti-1", "graffiti", 60, "approved"),
    ("graffiti-2", "graffiti", 90, "approved"),
    ("unreviewed", "roads", 45, "unreviewed"),
    ("unlocated", "roads", 45, "unlocated"),
    ("incompatible", "roads", 45, "incompatible"),
    ("unknown-duration", "roads", None, "unknown_duration"),
    ("oversized", "roads", 500, "approved"),
    ("lighting-inspection", "lighting", 20, "unreviewed"),
    ("historical", "roads", None, "historical"),
]


def source_examples(csv_path: Path) -> dict[str, list[dict[str, str]]]:
    """Scan for a handful of central, located source examples; do not import all."""
    candidates = {crew: [] for crew in ("roads", "cleanup", "graffiti", "lighting", "historical")}
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if set(reader.fieldnames or []) != SOURCE_FIELDS:
            raise ValueError("Dataset must contain the nine agreed source columns")
        for row in reader:
            mapping = CATEGORIES.get(row["NAME"])
            if mapping is None:
                continue
            crew = mapping[0]
            status = row["STATUS"].strip().upper()
            key = "historical" if status == "CLOSED" and crew == "roads" else crew
            if key not in candidates or len(candidates[key]) >= 12:
                continue
            if key != "historical" and status not in {"OPEN", "WAITING"}:
                continue
            location = csv_location(row)
            if location.lat is None or not (53.325 <= location.lat <= 53.37 and -6.30 <= location.lng <= -6.22):
                continue
            candidates[key].append(dict(row))
            if all(len(rows) >= 12 for rows in candidates.values()):
                break
    for crew, rows in candidates.items():
        if not rows:
            raise ValueError(f"No located central source example found for {crew}")
    return candidates


def seed_demo(database: Database, csv_path: Path) -> dict[str, int]:
    """Insert missing DEMO-* examples only; preserve dispatcher edits on repeats."""
    examples = source_examples(Path(csv_path))
    now = datetime.now(timezone.utc).isoformat()
    inserted = skipped = 0
    offsets = {crew: 0 for crew in examples}
    with database.sessions.begin() as session:
        existing = set(session.scalars(select(Issue.reference).where(Issue.reference.like("DEMO-%"))))
        for label, crew, minutes, scenario in SCENARIOS:
            reference = f"DEMO-{label.upper()}"
            key = "historical" if scenario == "historical" else crew
            rows = examples[key]
            row = rows[offsets[key] % len(rows)]
            offsets[key] += 1
            if reference in existing:
                skipped += 1
                continue
            historical = scenario == "historical"
            location = csv_location(row, confirmed=scenario != "unlocated")
            category = row["NAME"]
            _, task_type, capability = CATEGORIES[category]
            required = [capability]
            if scenario == "incompatible":
                required.append("graffiti_removal")
            analysis = Analysis(
                category=category, summary=("Historical source record; repair duration unknown" if historical else f"Synthetic demo scenario: {label}; duration is an invented estimate"),
                required_capabilities=required, time_cost_minutes=minutes,
                needs_inspection=task_type == "inspection", needs_review=scenario != "approved",
            )
            issue = Issue(
                reference=reference, created_at=now,
                incident_date=datetime.strptime(row["INCIDENT_DATE"], "%d/%m/%Y").date().isoformat() if historical else now[:10],
                description=None if historical else f"SYNTHETIC DEMO TASK ({label}), derived from historical incident {row['INCIDENT_NUMBER']}. Any duration is a synthetic estimate, not historical ground truth.",
                reporter_email=None, photo_filename=None, photo_media_type=None,
                address=row["INCIDENT_ADDRESS"], original_json=dict(row), source_status=row["STATUS"],
                lat=location.lat if scenario != "unlocated" else None,
                lng=location.lng if scenario != "unlocated" else None,
                location_source="csv", location_confirmed=location.confirmed and not historical,
                is_active=not historical, is_synthetic=not historical,
                analysis_state="complete", analysis_json=analysis.model_dump(),
                review_state="needs_review", crew=crew, task_type=task_type, estimated_minutes=minutes,
            )
            if scenario == "approved":
                blockers = task_blockers(issue, require_approval=False)
                if blockers:
                    raise ValueError(f"Cannot approve seed {reference}: {blockers[0].message}")
                issue.review_state = "approved"
            session.add(issue)
            inserted += 1
    return {"inserted": inserted, "skipped": skipped, "total_scenarios": len(SCENARIOS)}
