from unittest.mock import Mock

from app.models import Analysis
from app.services.osrm import PlanningError
from tests.test_classification import analysis_data
from tests.test_submissions import SubmissionCase


class PlanAPITests(SubmissionCase):
    def test_photo_to_classification_approval_and_plan(self):
        self.app.state.classifier = Mock()
        self.app.state.classifier.classify.return_value = Analysis(**analysis_data())
        report = self.submit(lat='53.34', lng='-6.26', location_confirmed='true').json()
        approved = self.client.patch(f"/api/issues/{report['id']}", json={'review_state': 'approved'})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.app.state.travel_provider = Mock()
        self.app.state.travel_provider.duration_matrix.return_value = [[0, 12], [15, 0]]
        result = self.client.post('/api/plan', json={'crew': 'roads'})
        self.assertEqual(result.status_code, 200, result.text)
        plan = result.json()
        self.assertEqual(plan['stops'][0]['report_id'], report['id'])
        self.assertEqual(plan['stops'][0]['arrive'], '08:12')
        self.assertEqual(plan['stops'][0]['complete'], '08:57')
        self.assertEqual(plan['totals'], {'travel_minutes': 27, 'task_minutes': 45})
        self.assertEqual(plan['lunch']['start'], '12:00')
        self.assertLessEqual(plan['depot_return'], '16:00')
        self.assertNotIn('email', result.text)

    def test_empty_plan_and_request_validation(self):
        self.app.state.travel_provider = Mock()
        result = self.client.post('/api/plan', json={'crew': 'roads'})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['stops'], [])
        self.app.state.travel_provider.duration_matrix.assert_not_called()
        for fields in ({'crew': 'unknown'}, {'crew': 'roads', 'extra': True}, {}):
            self.assertEqual(self.client.post('/api/plan', json=fields).status_code, 422)

    def test_osrm_failure_has_clear_error(self):
        self.app.state.classifier = Mock()
        self.app.state.classifier.classify.return_value = Analysis(**analysis_data())
        report = self.submit(lat='53.34', lng='-6.26', location_confirmed='true').json()
        self.client.patch(f"/api/issues/{report['id']}", json={'review_state': 'approved'})
        self.app.state.travel_provider = Mock()
        self.app.state.travel_provider.duration_matrix.side_effect = PlanningError('OSRM road travel times unavailable; please retry')
        result = self.client.post('/api/plan', json={'crew': 'roads'})
        self.assertEqual(result.status_code, 503)
        self.assertIn('OSRM', result.json()['detail']['message'])
