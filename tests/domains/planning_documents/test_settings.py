import os
import unittest
from unittest.mock import patch

from app.domains.planning_documents.settings import (
    PlanningAnalysisSettings,
)


class PlanningAnalysisSettingsTest(unittest.TestCase):
    def test_defaults_are_used_without_environment_variables(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = PlanningAnalysisSettings.from_env()

        self.assertEqual(
            settings.planning_analysis_timeout_seconds,
            180,
        )
        self.assertEqual(settings.planning_max_analysis_chunks, 2)
        self.assertEqual(settings.planning_analysis_retry_count, 0)

    def test_environment_variables_override_defaults(self):
        with patch.dict(
            os.environ,
            {
                "PLANNING_ANALYSIS_TIMEOUT_SECONDS": "240",
                "PLANNING_MAX_ANALYSIS_CHUNKS": "4",
                "PLANNING_ANALYSIS_RETRY_COUNT": "0",
            },
            clear=True,
        ):
            settings = PlanningAnalysisSettings.from_env()

        self.assertEqual(
            settings.planning_analysis_timeout_seconds,
            240,
        )
        self.assertEqual(settings.planning_max_analysis_chunks, 4)
        self.assertEqual(settings.planning_analysis_retry_count, 0)

    def test_invalid_values_are_rejected(self):
        invalid_environments = (
            {"PLANNING_ANALYSIS_TIMEOUT_SECONDS": "1"},
            {"PLANNING_MAX_ANALYSIS_CHUNKS": "1"},
            {"PLANNING_ANALYSIS_RETRY_COUNT": "-1"},
            {"PLANNING_ANALYSIS_RETRY_COUNT": "1"},
            {"PLANNING_ANALYSIS_TIMEOUT_SECONDS": "invalid"},
        )
        for environment in invalid_environments:
            with self.subTest(environment=environment):
                with (
                    patch.dict(
                        os.environ,
                        environment,
                        clear=True,
                    ),
                    self.assertRaises(ValueError),
                ):
                    PlanningAnalysisSettings.from_env()


if __name__ == "__main__":
    unittest.main()
