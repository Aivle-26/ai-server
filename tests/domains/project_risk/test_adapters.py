from datetime import datetime
import unittest

from app.domains.project_risk.adapters.github_adapter import GitHubAdapter
from app.domains.project_risk.adapters.jira_adapter import JiraAdapter
from app.domains.project_risk.adapters.slack_adapter import SlackAdapter
from app.domains.project_risk.services.normalization_service import (
    NormalizationService,
)


class ProjectRiskAdapterTest(unittest.TestCase):
    def test_github_issue_normalizes_priority_actor_and_metadata(self):
        result = GitHubAdapter().normalize(
            {
                "data_type": "ISSUE",
                "data": {
                    "number": 12,
                    "title": "Login is blocked",
                    "body": "Authentication fails",
                    "state": "open",
                    "labels": [{"name": "blocker"}],
                    "user": {"id": 42, "login": "kim"},
                    "created_at": "2026-07-28T01:00:00Z",
                    "html_url": "https://example.invalid/12",
                },
            }
        )

        self.assertEqual(result["source_type"], "GITHUB")
        self.assertEqual(result["event_type"], "ISSUE")
        self.assertEqual(result["priority"], "CRITICAL")
        self.assertEqual(result["actor_external_id"], "42")
        self.assertIsInstance(result["occurred_at"], datetime)
        self.assertEqual(result["metadata_json"]["issue_number"], 12)

    def test_github_pr_and_commit_contracts(self):
        adapter = GitHubAdapter()
        pull_request = adapter.normalize(
            {
                "data_type": "PR",
                "data": {
                    "number": 2,
                    "title": "Merge feature",
                    "merged": True,
                    "state": "closed",
                    "base": {"ref": "dev"},
                    "head": {"ref": "feature"},
                },
            }
        )
        commit = adapter.normalize(
            {
                "data_type": "COMMIT",
                "data": {
                    "sha": "abc",
                    "commit": {
                        "message": "fix",
                        "author": {
                            "name": "Kim",
                            "email": "dev@example.invalid",
                            "date": "2026-07-28T01:00:00Z",
                        },
                    },
                },
            }
        )

        self.assertEqual(pull_request["status"], "MERGED")
        self.assertEqual(
            pull_request["metadata_json"]["base_branch"], "dev"
        )
        self.assertEqual(commit["event_type"], "COMMIT")
        self.assertEqual(
            commit["actor_external_id"], "dev@example.invalid"
        )

    def test_jira_normalizes_issue_and_priority(self):
        result = JiraAdapter().normalize(
            {
                "data_type": "BUG",
                "data": {
                    "id": "100",
                    "key": "AIPM-1",
                    "fields": {
                        "summary": "API error",
                        "description": "Request fails",
                        "status": {"name": "In Progress"},
                        "priority": {"name": "Highest"},
                        "assignee": {"accountId": "member-1"},
                        "created": "2026-07-28T01:00:00+00:00",
                    },
                },
            }
        )

        self.assertEqual(result["event_type"], "BUG")
        self.assertEqual(result["status"], "IN PROGRESS")
        self.assertEqual(result["priority"], "CRITICAL")
        self.assertEqual(result["metadata_json"]["jira_key"], "AIPM-1")

    def test_slack_thread_priority_and_title_are_normalized(self):
        text = "긴급 서비스 중단 " + ("x" * 60)
        result = SlackAdapter().normalize(
            {
                "data_type": "MESSAGE",
                "data": {
                    "ts": "2026-07-28T01:00:00Z",
                    "thread_ts": "thread-1",
                    "text": text,
                    "user": "U-1",
                    "channel": "C-1",
                },
            }
        )

        self.assertEqual(result["event_type"], "THREAD_REPLY")
        self.assertEqual(result["priority"], "CRITICAL")
        self.assertEqual(len(result["title"]), 53)
        self.assertTrue(result["title"].endswith("..."))

    def test_unsupported_types_are_rejected(self):
        cases = (
            (GitHubAdapter(), {"data_type": "RELEASE"}),
            (JiraAdapter(), {"data_type": "SPRINT"}),
            (SlackAdapter(), {"data_type": "REACTION"}),
        )
        for adapter, payload in cases:
            with self.subTest(adapter=type(adapter).__name__), self.assertRaises(
                ValueError
            ):
                adapter.normalize(payload)

    def test_normalization_service_routes_source_case_insensitively(self):
        service = NormalizationService()
        result = service.normalize(
            "github",
            {
                "data_type": "ISSUE",
                "data": {
                    "title": "Issue",
                    "state": "open",
                    "labels": [],
                },
            },
        )
        self.assertEqual(result["source_type"], "GITHUB")
        with self.assertRaisesRegex(ValueError, "Adapter"):
            service.normalize("unknown", {})


if __name__ == "__main__":
    unittest.main()
