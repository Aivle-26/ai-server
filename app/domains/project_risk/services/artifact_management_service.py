from datetime import date, datetime
from typing import Any


class ArtifactManagementService:
    COMPLETED_STATUSES = {
        "APPROVED",
        "COMPLETED",
    }

    def build_register(
        self,
        project_id: int,
        required_artifacts: list[dict[str, Any]],
        stored_documents: list[dict[str, Any]],
        version_histories: list[dict[str, Any]],
        approval_histories: list[dict[str, Any]],
        reference_date: str | None = None,
    ) -> dict[str, Any]:
        if project_id <= 0:
            raise ValueError(
                "project_id는 1 이상의 값이어야 합니다."
            )

        today = self._parse_date(
            reference_date
        ) if reference_date else date.today()

        document_map = {
            document["artifact_code"]: document
            for document in stored_documents
            if document.get("artifact_code")
        }

        register: list[dict[str, Any]] = []
        uncompleted_artifacts: list[dict[str, Any]] = []

        for required in required_artifacts:
            artifact_code = required.get(
                "artifact_code"
            )

            if not artifact_code:
                raise ValueError(
                    "required_artifacts에는 "
                    "artifact_code가 필요합니다."
                )

            document = document_map.get(
                artifact_code
            )

            latest_version = (
                self._get_latest_version(
                    artifact_code=artifact_code,
                    version_histories=version_histories,
                )
            )

            latest_approval = (
                self._get_latest_approval(
                    artifact_code=artifact_code,
                    approval_histories=approval_histories,
                )
            )

            due_date = self._parse_date(
                required.get("due_date")
            )

            registered = document is not None

            approval_status = (
                latest_approval.get(
                    "approval_status"
                )
                if latest_approval
                else "NOT_REQUESTED"
            )

            version = (
                latest_version.get("version")
                if latest_version
                else None
            )

            artifact_status = (
                self._determine_status(
                    registered=registered,
                    approval_status=approval_status,
                    due_date=due_date,
                    reference_date=today,
                )
            )

            delay_days = self._calculate_delay_days(
                artifact_status=artifact_status,
                due_date=due_date,
                reference_date=today,
            )

            item = {
                "artifact_code": artifact_code,
                "artifact_name": required.get(
                    "artifact_name"
                ),
                "artifact_type": required.get(
                    "artifact_type"
                ),
                "required": required.get(
                    "required",
                    True,
                ),
                "owner": required.get("owner"),
                "due_date": (
                    due_date.isoformat()
                    if due_date
                    else None
                ),
                "registered": registered,
                "document_id": (
                    document.get("document_id")
                    if document
                    else None
                ),
                "storage_path": (
                    document.get("storage_path")
                    if document
                    else None
                ),
                "latest_version": version,
                "approval_status":
                    approval_status,
                "approved_by": (
                    latest_approval.get(
                        "approved_by"
                    )
                    if latest_approval
                    else None
                ),
                "status": artifact_status,
                "delay_days": delay_days,
                "requires_action":
                    artifact_status
                    not in self.COMPLETED_STATUSES,
            }

            register.append(item)

            if item["requires_action"]:
                uncompleted_artifacts.append(
                    {
                        **item,
                        "reason":
                            self._make_reason(
                                status=artifact_status
                            ),
                        "recommended_action":
                            self._make_action(
                                status=artifact_status
                            ),
                    }
                )

        summary = self._make_summary(
            register=register
        )

        return {
            "project_id": project_id,
            "reference_date": today.isoformat(),
            "artifact_summary": summary,
            "artifact_register": register,
            "uncompleted_artifacts":
                uncompleted_artifacts,
        }

    def _get_latest_version(
        self,
        artifact_code: str,
        version_histories: list[
            dict[str, Any]
        ],
    ) -> dict[str, Any] | None:
        histories = [
            history
            for history in version_histories
            if history.get("artifact_code")
            == artifact_code
        ]

        if not histories:
            return None

        return max(
            histories,
            key=lambda item: (
                self._version_key(
                    item.get("version")
                ),
                self._datetime_key(
                    item.get("created_at")
                ),
            ),
        )

    def _get_latest_approval(
        self,
        artifact_code: str,
        approval_histories: list[
            dict[str, Any]
        ],
    ) -> dict[str, Any] | None:
        histories = [
            history
            for history in approval_histories
            if history.get("artifact_code")
            == artifact_code
        ]

        if not histories:
            return None

        return max(
            histories,
            key=lambda item:
                self._datetime_key(
                    item.get("reviewed_at")
                ),
        )

    def _determine_status(
        self,
        registered: bool,
        approval_status: str,
        due_date: date | None,
        reference_date: date,
    ) -> str:
        normalized_approval = (
            str(approval_status).upper()
        )

        if not registered:
            if (
                due_date
                and reference_date > due_date
            ):
                return "OVERDUE_NOT_REGISTERED"

            return "NOT_REGISTERED"

        if normalized_approval == "APPROVED":
            return "APPROVED"

        if normalized_approval == "REJECTED":
            return "REJECTED"

        if normalized_approval in {
            "PENDING",
            "IN_REVIEW",
        }:
            if (
                due_date
                and reference_date > due_date
            ):
                return "OVERDUE_APPROVAL"

            return "PENDING_APPROVAL"

        if (
            due_date
            and reference_date > due_date
        ):
            return "OVERDUE_NOT_REQUESTED"

        return "REGISTERED_NOT_REQUESTED"

    def _calculate_delay_days(
        self,
        artifact_status: str,
        due_date: date | None,
        reference_date: date,
    ) -> int:
        if not due_date:
            return 0

        if not artifact_status.startswith(
            "OVERDUE"
        ):
            return 0

        return max(
            0,
            (reference_date - due_date).days,
        )

    def _make_summary(
        self,
        register: list[dict[str, Any]],
    ) -> dict[str, int | float]:
        total_count = len(register)

        approved_count = sum(
            1
            for item in register
            if item["status"] == "APPROVED"
        )

        registered_count = sum(
            1
            for item in register
            if item["registered"]
        )

        not_registered_count = sum(
            1
            for item in register
            if not item["registered"]
        )

        pending_count = sum(
            1
            for item in register
            if item["status"] in {
                "PENDING_APPROVAL",
                "REGISTERED_NOT_REQUESTED",
            }
        )

        rejected_count = sum(
            1
            for item in register
            if item["status"] == "REJECTED"
        )

        overdue_count = sum(
            1
            for item in register
            if item["status"].startswith(
                "OVERDUE"
            )
        )

        completion_rate = (
            round(
                approved_count
                / total_count
                * 100,
                2,
            )
            if total_count
            else 0.0
        )

        return {
            "total_artifact_count":
                total_count,
            "registered_count":
                registered_count,
            "approved_count":
                approved_count,
            "pending_count":
                pending_count,
            "rejected_count":
                rejected_count,
            "not_registered_count":
                not_registered_count,
            "overdue_count":
                overdue_count,
            "completion_rate":
                completion_rate,
        }

    def _make_reason(
        self,
        status: str,
    ) -> str:
        reasons = {
            "NOT_REGISTERED":
                "필수 산출물이 등록되지 않았습니다.",
            "OVERDUE_NOT_REGISTERED":
                "제출 기한이 지났지만 산출물이 "
                "등록되지 않았습니다.",
            "REGISTERED_NOT_REQUESTED":
                "산출물은 등록됐지만 승인 요청이 "
                "진행되지 않았습니다.",
            "OVERDUE_NOT_REQUESTED":
                "기한이 지났고 승인 요청도 "
                "진행되지 않았습니다.",
            "PENDING_APPROVAL":
                "승인 검토가 진행 중입니다.",
            "OVERDUE_APPROVAL":
                "승인 검토가 기한 내 완료되지 "
                "않았습니다.",
            "REJECTED":
                "승인이 반려되어 수정이 필요합니다.",
        }

        return reasons.get(
            status,
            "후속 조치가 필요합니다.",
        )

    def _make_action(
        self,
        status: str,
    ) -> str:
        actions = {
            "NOT_REGISTERED":
                "담당자에게 산출물 등록을 요청합니다.",
            "OVERDUE_NOT_REGISTERED":
                "담당자와 PM에게 지연 알림을 "
                "발송하고 제출 일정을 재설정합니다.",
            "REGISTERED_NOT_REQUESTED":
                "최신 버전을 확인한 뒤 승인 요청을 "
                "진행합니다.",
            "OVERDUE_NOT_REQUESTED":
                "즉시 승인 요청을 진행하고 "
                "지연 사유를 기록합니다.",
            "PENDING_APPROVAL":
                "승인 담당자에게 검토 상태를 "
                "확인합니다.",
            "OVERDUE_APPROVAL":
                "승인 담당자에게 검토 지연 알림을 "
                "발송합니다.",
            "REJECTED":
                "반려 사유를 반영해 새 버전을 "
                "등록합니다.",
        }

        return actions.get(
            status,
            "산출물 상태를 확인합니다.",
        )

    def _parse_date(
        self,
        value: Any,
    ) -> date | None:
        if value is None or value == "":
            return None

        if isinstance(value, date):
            return value

        return date.fromisoformat(
            str(value)[:10]
        )

    def _datetime_key(
        self,
        value: Any,
    ) -> datetime:
        if not value:
            return datetime.min

        if isinstance(value, datetime):
            return value

        normalized = str(value).replace(
            "Z",
            "+00:00",
        )

        try:
            parsed = datetime.fromisoformat(
                normalized
            )

            if parsed.tzinfo is not None:
                return parsed.replace(
                    tzinfo=None
                )

            return parsed

        except ValueError:
            return datetime.min

    def _version_key(
        self,
        value: Any,
    ) -> tuple[int, ...]:
        if value is None:
            return (0,)

        cleaned = str(value).lower().replace(
            "v",
            "",
        )

        parts: list[int] = []

        for part in cleaned.split("."):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)

        return tuple(parts)