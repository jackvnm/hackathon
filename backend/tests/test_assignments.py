import unittest
from unittest.mock import Mock

from app.assignments import assign_analysis
from app.models import Analysis
from tests import test_classification as classification
from tests import test_submissions as submissions


class AssignmentRulesTests(unittest.TestCase):
    def test_core_categories_map_to_expected_crew_and_task(self):
        for category, capability, crew, task in (
            ("Report Problem Road Surface", "road_surface_repair", "roads", "repair"),
            ("Illegal Dumping", "dumped_item_removal", "cleanup", "removal"),
            ("Report Graffiti", "graffiti_removal", "graffiti", "removal"),
        ):
            with self.subTest(category=category):
                analysis = Analysis(**classification.analysis_data(category=category, required_capabilities=[capability]))
                _, assignment = assign_analysis(analysis)
                self.assertEqual(assignment.crew, crew)
                self.assertEqual(assignment.task_type, task)
                self.assertEqual(assignment.estimated_minutes, 45)

    def test_specialists_require_separate_inspection_estimate(self):
        for category, crew, capability in (
            ("Public Lighting Repairs", "lighting", "lighting_inspection"),
            ("Tree Maintenance", "arborist", "arborist_inspection"),
            ("Report Gully Problem", "drainage", "drainage_inspection"),
        ):
            analysis = Analysis(**classification.analysis_data(category=category, required_capabilities=[capability]))
            updated, assignment = assign_analysis(analysis)
            self.assertEqual(assignment.crew, crew)
            self.assertEqual(assignment.task_type, "inspection")
            self.assertIsNone(assignment.estimated_minutes)
            self.assertTrue(updated.needs_inspection)
            self.assertTrue(updated.needs_review)
            analysis = Analysis(**classification.analysis_data(category=category, required_capabilities=[capability], needs_inspection=True, time_cost_minutes=20))
            _, assignment = assign_analysis(analysis)
            self.assertEqual(assignment.estimated_minutes, 20)

    def test_unknown_category_requires_manual_triage(self):
        updated, assignment = assign_analysis(Analysis(**classification.analysis_data(category="unsupported issue")))
        self.assertEqual(assignment.crew, "manual_triage")
        self.assertEqual(assignment.task_type, "manual_triage")
        self.assertIsNone(assignment.estimated_minutes)
        self.assertTrue(updated.needs_review)

    def test_unknown_duration_remains_unknown(self):
        _, assignment = assign_analysis(Analysis(**classification.analysis_data(time_cost_minutes=None)))
        self.assertIsNone(assignment.estimated_minutes)

    def test_conflicting_capabilities_require_review(self):
        updated, assignment = assign_analysis(Analysis(**classification.analysis_data(required_capabilities=["arborist_inspection"])))
        self.assertEqual(assignment.crew, "roads")
        self.assertTrue(updated.needs_review)
        self.assertIsNone(assignment.estimated_minutes)


class AssignmentIntegrationTests(submissions.SubmissionCase):
    def test_assignment_persists_without_automatic_approval(self):
        self.app.state.classifier = Mock()
        self.app.state.classifier.classify.return_value = Analysis(**classification.analysis_data())
        response = self.submit(lat="53.34", lng="-6.26", location_confirmed="true")
        self.assertEqual(response.status_code, 201, response.text)
        report = response.json()
        self.assertEqual(report["assignment"], {"crew": "roads", "task_type": "repair", "estimated_minutes": 45})
        self.assertEqual(report["review_state"], "needs_review")
        self.assertFalse(report["routable"])
        stored = self.app.state.store.get_issue(report["id"])
        self.assertEqual(stored.crew, "roads")
        self.assertEqual(stored.estimated_minutes, 45)
