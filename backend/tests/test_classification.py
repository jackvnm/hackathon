import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx2
from openai import OpenAI
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import Issue
from app.models import Analysis
from app.services.classification import OpenAIClassifier
from tests import test_submissions as submissions


def analysis_data(**updates):
    return {
        "category": "Report Problem Road Surface",
        "summary": "Visible pothole near the kerb",
        "required_capabilities": ["road_surface_repair"],
        "time_cost_minutes": 45,
        "needs_inspection": False,
        "needs_review": False,
        **updates,
    }


class ClassificationTests(submissions.SubmissionCase):
    def test_analysis_runs_after_commit_and_excludes_reporter_email(self):
        classifier = Mock()

        def classify(**inputs):
            issue = self.app.state.store.get_issue(1)
            self.assertIsNotNone(issue)
            self.assertEqual(issue.analysis_state, "pending")
            self.assertEqual((self.settings.photo_dir / issue.photo_filename).read_bytes(), self.photo)
            self.assertEqual(set(inputs), {"photo", "media_type", "description"})
            self.assertEqual(inputs["photo"], self.photo)
            self.assertNotIn("demo@example.com", str(inputs))
            return Analysis(**analysis_data())

        classifier.classify.side_effect = classify
        self.app.state.classifier = classifier
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["analysis_state"], "complete")
        self.assertEqual(response.json()["review_state"], "needs_review")
        self.assertFalse(response.json()["routable"])
        with self.app.state.database.sessions() as session:
            self.assertEqual(session.get(Issue, 1).analysis_json["time_cost_minutes"], 45)

    def test_api_failure_or_invalid_output_preserves_submission(self):
        for result in (RuntimeError("private upstream error"), analysis_data(time_cost_minutes=-1)):
            classifier = Mock()
            if isinstance(result, Exception):
                classifier.classify.side_effect = result
            else:
                classifier.classify.return_value = result
            self.app.state.classifier = classifier
            response = self.submit()
            self.assertEqual(response.status_code, 201, response.text)
            report = response.json()
            self.assertEqual(report["analysis_state"], "failed")
            self.assertEqual(report["review_state"], "needs_review")
            self.assertEqual(self.app.state.store.get_issue(report["id"]).analysis_state, "failed")
            self.assertEqual(self.client.get(report["photo_url"]).content, self.photo)
            self.assertNotIn("private upstream error", response.text)

    def test_missing_credentials_saves_report_with_clear_review_state(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["analysis_state"], "failed")
        self.assertIn("dispatcher review", response.json()["analysis_error"])

    def test_analysis_save_failure_does_not_claim_submission_was_lost(self):
        self.app.state.classifier = Mock()
        self.app.state.classifier.classify.return_value = Analysis(**analysis_data())
        with patch.object(self.app.state.store, "save_analysis", side_effect=SQLAlchemyError("failure")):
            response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["analysis_state"], "pending")
        self.assertIn("Report saved", response.json()["analysis_error"])
        self.assertEqual(self.app.state.store.get_issue(1).analysis_state, "pending")
        self.assertEqual(self.client.get(response.json()["photo_url"]).content, self.photo)

    def test_unknown_duration_and_strict_validation(self):
        self.assertIsNone(Analysis(**analysis_data(time_cost_minutes=None)).time_cost_minutes)
        for updates in ({"time_cost_minutes": 0}, {"time_cost_minutes": True}, {"needs_review": "false"}, {"unexpected": "value"}):
            with self.assertRaises(ValidationError):
                Analysis(**analysis_data(**updates))

    def test_official_sdk_sends_image_and_parses_structured_result(self):
        captured = []

        def transport(request):
            captured.append(json.loads(request.content))
            return httpx2.Response(200, json={
                "id": "resp_demo", "object": "response", "created_at": 0,
                "status": "completed", "model": "gpt-4.1-mini",
                "output": [{"id": "msg_demo", "type": "message", "status": "completed",
                            "role": "assistant", "content": [{"type": "output_text",
                            "text": json.dumps(analysis_data()), "annotations": []}]}],
            })

        client = OpenAI(api_key="synthetic-test-key", http_client=httpx2.Client(transport=httpx2.MockTransport(transport)))
        with patch("app.services.classification.OpenAI", return_value=client):
            classifier = OpenAIClassifier(Settings(data_dir=self.settings.data_dir, openai_api_key="synthetic-test-key"))
            result = classifier.classify(photo=self.photo, media_type="image/jpeg", description="Pothole at the kerb")
        self.assertEqual(result.time_cost_minutes, 45)
        request = captured[0]
        self.assertFalse(request["store"])
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        content = request["input"][0]["content"]
        self.assertEqual(content[0]["text"], "Pothole at the kerb")
        self.assertEqual(base64.b64decode(content[1]["image_url"].split(",", 1)[1]), self.photo)
        self.assertNotIn("demo@example.com", json.dumps(request))

    def test_refusal_or_incomplete_result_is_rejected(self):
        for status, parsed in (("completed", None), ("incomplete", Analysis(**analysis_data()))):
            fake = Mock()
            fake.__enter__ = Mock(return_value=fake)
            fake.__exit__ = Mock(return_value=False)
            fake.responses.parse.return_value = SimpleNamespace(status=status, output_parsed=parsed)
            with patch("app.services.classification.OpenAI", return_value=fake):
                classifier = OpenAIClassifier(Settings(data_dir=self.settings.data_dir, openai_api_key="synthetic-test-key"))
                with self.assertRaises(ValueError):
                    classifier.classify(photo=self.photo, media_type="image/jpeg", description="Pothole")
