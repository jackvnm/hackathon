import csv
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import MetaData, inspect, select

from app.config import Settings
from app.database import Database, Issue
from app.eligibility import task_blockers
from app.services.demo_data import SOURCE_FIELDS, seed_demo


class DemoDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Database(Settings(data_dir=Path(self.temp.name)))
        self.addCleanup(self.database.close)
        self.source = Path(self.temp.name) / "source.csv"
        with self.source.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=sorted(SOURCE_FIELDS))
            writer.writeheader()
            for index, (category, status) in enumerate([
                ("Report Problem Road Surface", "OPEN"),
                ("Illegal Dumping", "WAITING"),
                ("Report Graffiti", "OPEN"),
                ("Public Lighting Repairs", "WAITING"),
                ("Report Problem Road Surface", "CLOSED"),
            ]):
                writer.writerow({
                    "INCIDENT_NUMBER": str(index + 1), "SR_CREATION_CHANNEL": "WEB",
                    "INCIDENT_ADDRESS": "Clearly identified fixture street", "STATUS": status,
                    "GROUP_NAME": "Fixture department", "NAME": category,
                    "INCIDENT_DATE": "01/09/2009", "ATTRIBUTE5": "715891.45", "ATTRIBUTE6": "734211.02",
                })

    def test_seed_preserves_source_and_dispatcher_edits_and_excludes_invalid_tasks(self):
        self.database.initialize()
        self.assertEqual(seed_demo(self.database, self.source)["inserted"], 15)
        with self.database.sessions.begin() as session:
            issues = list(session.scalars(select(Issue)))
            self.assertEqual(len(issues), 15)
            for issue in issues:
                self.assertIsNone(issue.reporter_email)
                self.assertIsNone(issue.photo_filename)
                self.assertEqual(set(issue.original_json), SOURCE_FIELDS)
                self.assertEqual(issue.original_json["INCIDENT_DATE"], "01/09/2009")
                self.assertEqual(issue.source_status, issue.original_json["STATUS"])
                if issue.review_state == "approved":
                    self.assertEqual(task_blockers(issue), [])
                elif issue.reference == "DEMO-HISTORICAL":
                    self.assertFalse(issue.is_active)
                    self.assertFalse(issue.is_synthetic)
                    self.assertIsNone(issue.description)
                    self.assertIn("inactive", [b.reason for b in task_blockers(issue)])
                else:
                    self.assertIn("SYNTHETIC", issue.description)
                    self.assertTrue(task_blockers(issue))
            edited = next(issue for issue in issues if issue.reference == "DEMO-ROADS-1")
            edited.estimated_minutes = 71
        self.assertEqual(seed_demo(self.database, self.source), {"inserted": 0, "skipped": 15, "total_scenarios": 15})
        with self.database.sessions() as session:
            self.assertEqual(session.scalar(select(Issue).where(Issue.reference == "DEMO-ROADS-1")).estimated_minutes, 71)

    def test_existing_nonnullable_database_is_backed_up_and_preserved(self):
        self.database.settings.photo_dir.mkdir(parents=True)
        old_table = Issue.__table__.to_metadata(MetaData())
        for field in ("description", "reporter_email", "photo_filename", "photo_media_type"):
            old_table.c[field].nullable = False
        old_table.create(self.database.engine)
        with self.database.sessions.begin() as session:
            session.add(Issue(
                id=8, reference="CIV-000008", created_at="2026-10-04T08:00:00+00:00", incident_date="2026-10-04",
                description="Existing submission", reporter_email="fixture@example.com",
                photo_filename="original.jpg", photo_media_type="image/jpeg", location_source="none", is_active=True,
            ))
        with self.database.sessions.begin() as session:
            deleted = Issue(
                id=99, reference="CIV-000099", created_at="2026-10-04T08:00:00+00:00", incident_date="2026-10-04",
                description="Deleted fixture", reporter_email="fixture@example.com",
                photo_filename="deleted.jpg", photo_media_type="image/jpeg", location_source="none", is_active=True,
            )
            session.add(deleted)
            session.flush()
            session.delete(deleted)
        photo = self.database.settings.photo_dir / "original.jpg"
        photo.write_bytes(b"Synthetic photo fixture")
        self.database.initialize()
        self.assertEqual(len(list(Path(self.temp.name).glob("issues.pre-nullable-*.sqlite3"))), 1)
        with self.database.sessions() as session:
            preserved = session.get(Issue, 8)
            self.assertEqual(preserved.reporter_email, "fixture@example.com")
            self.assertEqual(preserved.photo_filename, "original.jpg")
        self.assertEqual(photo.read_bytes(), b"Synthetic photo fixture")
        self.assertTrue(all(column["nullable"] for column in inspect(self.database.engine).get_columns("issues") if column["name"] in {"description", "reporter_email", "photo_filename", "photo_media_type"}))
        self.assertEqual(seed_demo(self.database, self.source)["inserted"], 15)
        with self.database.sessions() as session:
            self.assertTrue(all(issue.id > 99 for issue in session.scalars(select(Issue).where(Issue.reference.like("DEMO-%")))))
        self.database.initialize()
        self.assertEqual(len(list(Path(self.temp.name).glob("issues.pre-nullable-*.sqlite3"))), 1)


if __name__ == "__main__":
    unittest.main()
