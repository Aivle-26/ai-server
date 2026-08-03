import unittest

from pydantic import ValidationError

from app.domains.planning_schedule.schemas import PlanningScheduleRequest
from tests.fixtures.planning_samples import schedule_request_payload


class PlanningScheduleSchemaTest(unittest.TestCase):
    def test_valid_request_ignores_extra_wbs_fields(self):
        payload = schedule_request_payload()
        payload["wbs_items"][2]["mapped_requirement_ids"] = [1]

        request = PlanningScheduleRequest.model_validate(payload)
        self.assertEqual(request.wbs_items[2].wbs_id, 3)
        self.assertFalse(
            hasattr(request.wbs_items[2], "mapped_requirement_ids")
        )

    def test_target_end_must_not_precede_start(self):
        payload = schedule_request_payload()
        payload["target_end_date"] = "2026-08-02"
        with self.assertRaises(ValidationError):
            PlanningScheduleRequest.model_validate(payload)

    def test_request_rejects_duplicate_ids_codes_and_blank_values(self):
        cases = []
        duplicate_id = schedule_request_payload()
        duplicate_id["wbs_items"][1]["wbs_id"] = 1
        cases.append(duplicate_id)
        duplicate_code = schedule_request_payload()
        duplicate_code["wbs_items"][1]["wbs_code"] = "1"
        cases.append(duplicate_code)
        blank_name = schedule_request_payload()
        blank_name["wbs_items"][2]["wbs_name"] = " "
        cases.append(blank_name)

        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                PlanningScheduleRequest.model_validate(payload)

    def test_request_rejects_missing_task_and_invalid_parent(self):
        no_task = schedule_request_payload()
        no_task["wbs_items"] = no_task["wbs_items"][:2]
        bad_parent = schedule_request_payload()
        bad_parent["wbs_items"][2]["parent_wbs_id"] = 1

        for payload in (no_task, bad_parent):
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                PlanningScheduleRequest.model_validate(payload)

    def test_non_task_without_task_descendant_is_rejected(self):
        payload = schedule_request_payload()
        payload["wbs_items"] = payload["wbs_items"][:3] + payload["wbs_items"][3:5]
        with self.assertRaisesRegex(ValidationError, "하위 TASK"):
            PlanningScheduleRequest.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
