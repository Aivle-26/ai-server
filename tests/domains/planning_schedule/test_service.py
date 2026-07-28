import unittest

from app.domains.planning_schedule.llm_service import (
    GeneratedSchedulePlan,
    GeneratedTaskScheduleEstimate,
)
from app.domains.planning_schedule.schemas import PlanningScheduleRequest
from app.domains.planning_schedule.service import PlanningScheduleService
from tests.fixtures.planning_samples import schedule_request_payload


def estimate(wbs_id, predecessors=None, durations=(2, 3, 5)):
    return GeneratedTaskScheduleEstimate(
        wbs_id=wbs_id,
        optimistic_days=durations[0],
        most_likely_days=durations[1],
        pessimistic_days=durations[2],
        predecessor_wbs_ids=predecessors or [],
    )


class PlanningScheduleServiceTest(unittest.TestCase):
    def setUp(self):
        self.request = PlanningScheduleRequest.model_validate(
            schedule_request_payload()
        )
        self.service = PlanningScheduleService(
            monte_carlo_iterations=100, random_seed=7
        )

    def test_constructor_rejects_too_few_monte_carlo_iterations(self):
        with self.assertRaisesRegex(ValueError, "최소 100회"):
            PlanningScheduleService(monte_carlo_iterations=99)

    def test_context_contains_only_sorted_tasks_and_parent_names(self):
        context = self.service.prepare_context(self.request)

        self.assertEqual(
            [task["wbs_id"] for task in context["tasks"]], [3, 6]
        )
        self.assertEqual(context["tasks"][0]["phase_name"], "Analysis")
        self.assertEqual(
            context["tasks"][1]["work_package_name"], "Backend"
        )

    def test_invalid_and_future_predecessors_are_removed_with_warnings(self):
        plan = GeneratedSchedulePlan(
            task_estimates=[
                estimate(3, [999, 6]),
                estimate(6, [3, 3]),
            ]
        )

        result = self.service.build_schedule(self.request, plan)

        self.assertTrue(
            any("존재하지 않는 선행" in item for item in result["warnings"])
        )
        self.assertTrue(
            any("순서가 잘못된 선행" in item for item in result["warnings"])
        )
        schedule_by_id = {
            item["wbs_id"]: item for item in result["wbs_schedules"]
        }
        self.assertGreaterEqual(
            schedule_by_id[6]["expected"]["start_date"],
            schedule_by_id[3]["expected"]["end_date"],
        )

    def test_duplicate_estimates_use_first_value(self):
        plan = GeneratedSchedulePlan(
            task_estimates=[
                estimate(3, durations=(1, 1, 1)),
                estimate(3, durations=(10, 10, 10)),
                estimate(6, predecessors=[3], durations=(1, 1, 1)),
            ]
        )
        estimate_map = self.service._estimate_map(plan)
        self.assertEqual(estimate_map[3].most_likely_days, 1)

    def test_reversed_llm_duration_values_are_sorted_before_simulation(self):
        plan = GeneratedSchedulePlan(
            task_estimates=[
                estimate(3, durations=(8, 2, 5)),
                estimate(6, predecessors=[3], durations=(3, 1, 2)),
            ]
        )

        result = self.service.build_schedule(self.request, plan)
        for item in result["wbs_schedules"]:
            self.assertLessEqual(
                item["expected"]["end_date"],
                item["conservative"]["end_date"],
            )


if __name__ == "__main__":
    unittest.main()
