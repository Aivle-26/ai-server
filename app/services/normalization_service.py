from typing import Any

from app.adapters.github_adapter import GitHubAdapter
from app.adapters.jira_adapter import JiraAdapter
from app.adapters.slack_adapter import SlackAdapter


class NormalizationService:

    def __init__(self):
        self.adapters = {
            "GITHUB": GitHubAdapter(),
            "SLACK": SlackAdapter(),
            "JIRA": JiraAdapter(),
        }

    def normalize(
        self,
        source_type: str,
        payload: dict[str, Any]
    ) -> dict:
        adapter = self.adapters.get(
            source_type.upper()
        )

        if adapter is None:
            raise ValueError(
                f"{source_type} Adapter가 존재하지 않습니다."
            )

        return adapter.normalize(payload)