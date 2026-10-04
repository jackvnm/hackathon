from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.database import Issue
from app.eligibility import task_blockers
from app.main import create_app
from app.models import Analysis
from tests.test_classification import analysis_data
from tests.test_submissions import SubmissionCase


class ReviewTests(SubmissionCase):
    def setUp(self):
        super().setUp()
        self.app.state.classifier = Mock()
        self.app.state.classifier.classify.return_value = Analysis(**analysis_data())
        self.report = self.submit(lat="53.34", lng="-6.26", location_confirmed="true").json()
        self.url = f"/api/issues/{self.report['id']}"

    def update(self, **fields):
        return self.client.patch(self.url, json=fields)

    def test_listing_filter_shape_and_privacy(self):
        reports = self.client.get("/api/issues").json()
        self.assertEqual(reports, [self.report])
        self.assertEqual(self.client.get("/api/issues?crew=roads").json(), reports)
        self.assertEqual(self.client.get("/api/issues?crew=cleanup").json(), [])
        self.assertEqual(self.client.get("/api/issues?crew=bogus").status_code, 422)
        self.assertNotIn("email", str(reports))
        self.assertNotIn("photo_filename", str(reports))
        self.assertNotIn(self.temp.name, str(reports))

    def test_approval_and_each_change_invalidates(self):
        for fields in (
            {"crew": "cleanup"}, {"task_type": "inspection"},
            {"estimated_minutes": 46}, {"estimated_minutes": None},
            {"location": {"lat": 53.35, "lng": -6.26, "confirmed": True}},
            {"location": {"lat": 53.34, "lng": -6.26, "confirmed": False}},
        ):
            with self.subTest(fields=fields):
                restore = self.update(crew="roads", task_type="repair", estimated_minutes=45,
                    location={"lat": 53.34, "lng": -6.26, "confirmed": True}, review_state="approved")
                self.assertEqual(restore.status_code, 200, restore.text)
                self.assertTrue(restore.json()["routable"])
                changed = self.update(**fields)
                self.assertEqual(changed.status_code, 200, changed.text)
                self.assertEqual(changed.json()["review_state"], "needs_review")
                self.assertFalse(changed.json()["routable"])

    def test_noop_and_explicit_reapproval(self):
        self.assertTrue(self.update(review_state="approved").json()["routable"])
        self.assertTrue(self.update(estimated_minutes=45).json()["routable"])
        self.assertTrue(self.update(estimated_minutes=50, review_state="approved").json()["routable"])
        self.assertFalse(self.update(review_state="needs_review").json()["routable"])

    def test_rejected_approval_rolls_back_all_changes(self):
        response = self.update(crew="cleanup", task_type="removal", estimated_minutes=30, review_state="approved")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["field"], "crew")
        self.assertEqual(self.client.get("/api/issues").json(), [self.report])

    def test_approval_requires_complete_result(self):
        for fields, field in (
            ({"estimated_minutes": None}, "estimated_minutes"),
            ({"location": {"lat": None, "lng": None, "confirmed": False}}, "location"),
            ({"crew": "manual_triage"}, "crew"),
            ({"task_type": "removal", "estimated_minutes": 45}, "task_type"),
        ):
            response = self.update(**fields, review_state="approved")
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(response.json()["detail"]["field"], field)
            self.assertEqual(self.client.get("/api/issues").json(), [self.report])

    def test_unknown_repair_to_separately_approved_inspection(self):
        self.update(estimated_minutes=None)
        response = self.update(task_type="inspection", estimated_minutes=20, review_state="approved")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["routable"])
        response = self.update(task_type="repair")
        self.assertEqual(response.json()["review_state"], "needs_review")
        self.assertIsNone(response.json()["assignment"]["estimated_minutes"])
        self.assertEqual(self.update(review_state="approved").status_code, 422)

    def test_task_change_does_not_reuse_estimate(self):
        response = self.update(task_type="inspection", review_state="approved")
        self.assertEqual(response.status_code, 422)
        response = self.update(task_type="inspection")
        self.assertIsNone(response.json()["assignment"]["estimated_minutes"])

    def test_failed_analysis_can_be_manually_triaged(self):
        self.app.state.classifier.classify.side_effect = RuntimeError("synthetic failure")
        failed = self.submit().json()
        response = self.client.patch(f"/api/issues/{failed['id']}", json={
            "crew": "graffiti", "task_type": "removal", "estimated_minutes": 30,
            "location": {"lat": 53.34, "lng": -6.26, "confirmed": True},
            "review_state": "approved",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["routable"])
        self.assertEqual(response.json()["analysis_state"], "failed")

    def test_invalid_patch_and_not_found(self):
        for fields in (
            {"crew": "unknown"}, {"task_type": "unknown"}, {"estimated_minutes": 0},
            {"estimated_minutes": -1}, {"estimated_minutes": True}, {"estimated_minutes": "45"},
            {"crew": None}, {"location": None}, {"review_state": None},
            {"photo_url": "fake"}, {"email": "private@example.com"},
            {"location": {"lat": 91, "lng": 0, "confirmed": True}},
            {"location": {"lat": 53, "lng": None, "confirmed": False}},
            {"location": {"lat": None, "lng": None, "confirmed": True}},
            {"location": {"lat": 53, "lng": -6}},
        ):
            with self.subTest(fields=fields):
                self.assertEqual(self.update(**fields).status_code, 422)
        self.assertEqual(self.client.patch("/api/issues/999", json={}).status_code, 404)

    def test_source_and_restart_persistence(self):
        self.update(review_state="approved")
        with TestClient(create_app(self.settings)) as restarted:
            self.assertTrue(restarted.get("/api/issues").json()[0]["routable"])
        self.update(location={"lat": 53.35, "lng": -6.25, "confirmed": True})
        self.assertEqual(self.client.get("/api/issues").json()[0]["location"]["source"], "map_pin")
        self.update(location={"lat": None, "lng": None, "confirmed": False})
        self.assertEqual(self.client.get("/api/issues").json()[0]["location"]["source"], "none")

    def test_storage_errors_are_explicit(self):
        with patch.object(self.app.state.database.sessions, "begin", side_effect=SQLAlchemyError("synthetic")):
            response = self.update(review_state="approved")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get("/api/issues").json(), [self.report])

    def test_eligibility_historical_and_selected_crew(self):
        self.update(review_state="approved")
        for updates, expected in (
            ({"is_active": False}, "inactive"),
            ({"source_status": "CLOSED"}, "inactive"),
            ({"original_json": {"STATUS": "CLOSED"}}, "inactive"),
            ({"lat": float("inf")}, "unlocated"),
            ({"location_confirmed": False}, "unlocated"),
            ({"estimated_minutes": None}, "unknown_duration"),
            ({"analysis_json": {**analysis_data(), "required_capabilities": ["graffiti_removal"]}}, "incompatible_crew"),
        ):
            with self.subTest(updates=updates):
                issue = self.app.state.store.get_issue(self.report["id"])
                for field, value in updates.items():
                    setattr(issue, field, value)
                self.assertIn(expected, [b.reason for b in task_blockers(issue)])
        issue = self.app.state.store.get_issue(self.report["id"])
        self.assertIn("incompatible_crew", [b.reason for b in task_blockers(issue, "cleanup")])
        self.assertEqual(task_blockers(issue, "roads"), [])
        issue.source_status = "CLOSED"
        issue.is_synthetic = True
        self.assertEqual(task_blockers(issue), [])
        issue.is_active = False
        self.assertIn("inactive", [b.reason for b in task_blockers(issue)])

    def test_historical_approval_rejected_and_original_unchanged(self):
        with self.app.state.database.sessions.begin() as session:
            issue = session.get(Issue, self.report["id"])
            issue.source_status = "CLOSED"
            issue.original_json = {"STATUS": "CLOSED"}
        response = self.update(review_state="approved")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/issues").json()[0]["original"], {"STATUS": "CLOSED"})
