import unittest
from unittest.mock import Mock, patch

import httpx

from app.database import Issue
from app.services.osrm import OSRMClient, PlanningError
from app.services.planning import plan_day

DEPOT = (53.34, -6.26)


def issue(identifier, duration, **overrides):
    fields = dict(id=identifier, crew="roads", task_type="repair", estimated_minutes=duration,
        lat=53.34 + identifier / 1000, lng=-6.26, location_confirmed=True,
        is_active=True, is_synthetic=True, review_state="approved", analysis_json=None)
    fields.update(overrides)
    return Issue(**fields)


class PlanningTests(unittest.TestCase):
    def plan(self, reports, matrix):
        provider = Mock()
        provider.duration_matrix.return_value = matrix
        return plan_day(reports, "roads", DEPOT, provider)

    def test_travel_and_task_crossing_noon(self):
        reports = [issue(1, 200), issue(2, 30)]
        plan = self.plan(reports, [[0, 10, 500], [10, 0, 40], [10, 40, 0]])
        self.assertEqual(plan["stops"][0]["complete"], "11:30")
        self.assertEqual(plan["stops"][1]["arrive"], "13:40")
        self.assertEqual(plan["lunch"]["lat"], reports[0].lat)
        plan = self.plan([issue(1, 200), issue(2, 40)], [[0, 10, 500], [10, 0, 20], [10, 20, 0]])
        self.assertEqual(plan["stops"][1]["arrive"], "11:50")
        self.assertEqual(plan["stops"][1]["complete"], "13:40")
        self.assertEqual(plan["lunch"]["lat"], reports[1].lat)

    def test_return_crossing_lunch_and_early_return(self):
        report = issue(1, 200)
        plan = self.plan([report], [[0, 10], [40, 0]])
        self.assertEqual(plan["depot_return"], "13:40")
        self.assertEqual(plan["lunch"]["lat"], report.lat)
        plan = self.plan([report], [[0, 10], [10, 0]])
        self.assertEqual(plan["depot_return"], "11:40")
        self.assertEqual(plan["lunch"]["lat"], DEPOT[0])
        self.assertEqual(plan["totals"], {"travel_minutes": 20, "task_minutes": 200})

    def test_exact_shift_boundary_and_oversized(self):
        plan = self.plan([issue(1, 240), issue(2, 180), issue(3, 421)],
            [[0, 0, 300, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.assertEqual([stop["report_id"] for stop in plan["stops"]], [1, 2])
        self.assertEqual(plan["stops"][1]["complete"], "16:00")
        self.assertEqual(plan["depot_return"], "16:00")
        self.assertEqual(plan["totals"]["task_minutes"], 420)
        self.assertEqual(plan["omitted"][0]["reason"], "oversized")
        plan = self.plan([issue(1, 240), issue(2, 180)], [[0, 0, 300], [0, 0, 0], [1, 0, 0]])
        self.assertEqual([stop["report_id"] for stop in plan["stops"]], [1])

    def test_eligibility_and_empty_without_osrm(self):
        reports = [issue(1, 30, review_state="needs_review"), issue(2, 30, location_confirmed=False, review_state="needs_review"),
            issue(3, None, review_state="needs_review"), issue(4, 30, crew="cleanup", task_type="removal"),
            issue(5, 30, source_status="CLOSED", is_synthetic=False),
            issue(6, 30, crew="manual_triage", task_type="manual_triage")]
        provider = Mock()
        plan = plan_day(reports, "roads", DEPOT, provider)
        self.assertEqual([entry["reason"] for entry in plan["omitted"]],
            ["unapproved", "unlocated", "unknown_duration", "incompatible_crew", "inactive", "manual_triage"])
        self.assertEqual(plan["stops"], [])
        provider.duration_matrix.assert_not_called()
        self.assertEqual(plan["depot_return"], "08:00")

    def test_provider_failure_and_limit(self):
        provider = Mock()
        provider.duration_matrix.side_effect = PlanningError("Road travel times unavailable")
        with self.assertRaises(PlanningError):
            plan_day([issue(1, 30)], "roads", DEPOT, provider)
        with self.assertRaises(PlanningError):
            plan_day([issue(index, 30) for index in range(100)], "roads", DEPOT, Mock())

    def test_osrm_rounding_and_invalid_matrix(self):
        client = OSRMClient("https://osrm.example")
        with patch("app.services.osrm.httpx.Client") as factory:
            response = factory.return_value.__enter__.return_value.get.return_value
            response.json.return_value = {"code": "Ok", "durations": [[0, 61], [1, 0]]}
            self.assertEqual(client.duration_matrix([DEPOT, (53.35, -6.25)]), [[0, 2], [1, 0]])
            factory.return_value.__enter__.return_value.get.assert_called_once_with(
                "https://osrm.example/table/v1/driving/-6.26,53.34;-6.25,53.35", params={"annotations": "duration"})
            for invalid in ([[0, None], [1, 0]], [[0, -1], [1, 0]], [[0, float("inf")], [1, 0]], [[0]], [[0, True], [1, 0]]):
                response.json.return_value = {"code": "Ok", "durations": invalid}
                with self.subTest(invalid=invalid), self.assertRaises(PlanningError):
                    client.duration_matrix([DEPOT, (53.35, -6.25)])
            factory.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError("synthetic")
            with self.assertRaises(PlanningError):
                client.duration_matrix([DEPOT])
