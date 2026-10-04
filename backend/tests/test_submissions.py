import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from app.database import Issue

from app.config import Settings
from app.main import create_app


def photo_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, format="JPEG")
    return buffer.getvalue()


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name))
        self.app = create_app(self.settings)
        self.client = self.enterContext(TestClient(self.app))
        self.photo = photo_bytes()

    def submit(self, **fields):
        return self.client.post("/api/issues", data={"description": "Pothole at the kerb", "email": "demo@example.com", **fields}, files={"photo": ("../../unsafe.jpg", self.photo, "image/jpeg")})

    def test_saved_original_and_private_email_survive_restart(self):
        response = self.submit(address="Demo street")
        self.assertEqual(response.status_code, 201, response.text)
        report = response.json()
        self.assertEqual(report["reference"], "CIV-000001")
        self.assertEqual(report["analysis_state"], "pending")
        self.assertEqual(report["review_state"], "needs_review")
        self.assertFalse(report["routable"])
        self.assertNotIn("email", response.text)
        self.assertNotIn(self.temp.name, response.text)
        self.assertEqual(report["location"]["source"], "none")
        self.assertFalse(report["location"]["confirmed"])
        with TestClient(create_app(self.settings)) as restarted:
            self.assertEqual(restarted.get(report["photo_url"]).content, self.photo)
            other = restarted.post("/api/issues", data={"description": "Another pothole", "email": "demo@example.com"}, files={"photo": ("demo.jpg", self.photo, "image/jpeg")})
            self.assertNotEqual(other.json()["reference"], report["reference"])
        with self.app.state.database.sessions() as session:
            row = session.get(Issue, report["id"])
        self.assertEqual(row.reporter_email, "demo@example.com")
        self.assertEqual(row.is_active, 1)
        self.assertEqual((self.settings.photo_dir / row.photo_filename).read_bytes(), self.photo)

    def test_confirmed_and_unconfirmed_pins(self):
        for confirmed in (True, False):
            response = self.submit(lat="53.34", lng="-6.26", location_confirmed=str(confirmed).lower())
            self.assertEqual(response.status_code, 201, response.text)
            location = response.json()["location"]
            self.assertEqual(location["source"], "map_pin")
            self.assertEqual(location["lat"], 53.34)
            self.assertEqual(location["confirmed"], confirmed)
            self.assertFalse(response.json()["routable"])

    def test_invalid_form_does_not_save(self):
        for fields in ({"description": "  "}, {"email": "invalid"}, {"lat": "53"}, {"lat": "91", "lng": "0"}, {"lat": "nan", "lng": "0"}, {"location_confirmed": "true"}):
            with self.subTest(fields=fields):
                self.assertEqual(self.submit(**fields).status_code, 422)
        self.assertEqual(list(self.settings.photo_dir.iterdir()), [])

    def test_invalid_image_is_rejected(self):
        self.photo = b"not an image"
        self.assertEqual(self.submit().status_code, 422)
        self.assertEqual(list(self.settings.photo_dir.iterdir()), [])

    def test_oversized_upload_is_rejected(self):
        self.photo = b"x" * (self.settings.max_photo_bytes + 1)
        self.assertEqual(self.submit().status_code, 413)
        self.assertEqual(list(self.settings.photo_dir.iterdir()), [])

    def test_database_failure_cleans_up_photo(self):
        with patch.object(self.app.state.database.sessions, "begin", side_effect=SQLAlchemyError("test failure")):
            response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertIn("Submission not saved", response.text)
        self.assertEqual(list(self.settings.photo_dir.iterdir()), [])

    def test_photo_not_found(self):
        self.assertEqual(self.client.get("/api/issues/999/photo").status_code, 404)


if __name__ == "__main__":
    unittest.main()
