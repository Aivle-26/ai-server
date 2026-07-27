import re
from typing import Any


class ArtifactSecurityService:
    def inspect(
        self,
        file_name: str,
        document_type: str,
        text_content: str,
    ) -> dict[str, Any]:
        if not file_name.strip():
            raise ValueError("파일명이 비어 있습니다.")

        if not text_content.strip():
            raise ValueError(
                "검사할 문서 내용이 비어 있습니다."
            )

        privacy_findings = (
            self._detect_personal_information(
                text_content=text_content,
            )
        )

        confidentiality_findings = (
            self._detect_confidential_information(
                text_content=text_content,
            )
        )

        risk_score = self._calculate_risk_score(
            privacy_findings=privacy_findings,
            confidentiality_findings=(
                confidentiality_findings
            ),
        )

        risk_level = self._get_risk_level(
            score=risk_score,
        )

        contains_personal_information = (
            len(privacy_findings) > 0
        )

        contains_confidential_information = (
            len(confidentiality_findings) > 0
        )

        registration_allowed = (
            risk_level in {"LOW", "MEDIUM"}
        )

        return {
            "file": {
                "file_name": file_name,
                "document_type":
                    document_type.strip().upper(),
                "character_count": len(text_content),
            },
            "inspection": {
                "contains_personal_information":
                    contains_personal_information,
                "contains_confidential_information":
                    contains_confidential_information,
                "privacy_finding_count":
                    len(privacy_findings),
                "confidentiality_finding_count":
                    len(confidentiality_findings),
                "risk_score": risk_score,
                "risk_level": risk_level,
                "registration_allowed":
                    registration_allowed,
                "requires_review":
                    risk_level in {
                        "HIGH",
                        "CRITICAL",
                    },
            },
            "privacy_findings":
                privacy_findings,
            "confidentiality_findings":
                confidentiality_findings,
            "masked_preview":
                self._mask_sensitive_information(
                    text_content=text_content,
                )[:1000],
            "recommended_actions":
                self._make_recommended_actions(
                    privacy_findings=privacy_findings,
                    confidentiality_findings=(
                        confidentiality_findings
                    ),
                    risk_level=risk_level,
                ),
        }

    def _detect_personal_information(
        self,
        text_content: str,
    ) -> list[dict[str, Any]]:
        pattern_configs = {
            "RESIDENT_REGISTRATION_NUMBER": {
                "label": "주민등록번호",
                "pattern": (
                    r"\b\d{6}-?[1-4]\d{6}\b"
                ),
                "severity": "CRITICAL",
            },
            "PHONE_NUMBER": {
                "label": "휴대전화번호",
                "pattern": (
                    r"\b01[016789]-?"
                    r"\d{3,4}-?\d{4}\b"
                ),
                "severity": "HIGH",
            },
            "EMAIL_ADDRESS": {
                "label": "이메일 주소",
                "pattern": (
                    r"\b[A-Za-z0-9._%+-]+"
                    r"@[A-Za-z0-9.-]+"
                    r"\.[A-Za-z]{2,}\b"
                ),
                "severity": "MEDIUM",
            },
            "CARD_NUMBER": {
                "label": "카드번호",
                "pattern": (
                    r"\b(?:\d{4}[- ]?){3}"
                    r"\d{4}\b"
                ),
                "severity": "CRITICAL",
            },
            "IP_ADDRESS": {
                "label": "IP 주소",
                "pattern": (
                    r"\b(?:\d{1,3}\.){3}"
                    r"\d{1,3}\b"
                ),
                "severity": "MEDIUM",
            },
        }

        findings: list[dict[str, Any]] = []

        for finding_type, config in (
            pattern_configs.items()
        ):
            matches = re.findall(
                config["pattern"],
                text_content,
            )

            for match in dict.fromkeys(matches):
                findings.append(
                    {
                        "finding_type":
                            finding_type,
                        "label":
                            config["label"],
                        "severity":
                            config["severity"],
                        "detected_value":
                            self._mask_value(
                                value=match,
                            ),
                    }
                )

        return findings

    def _detect_confidential_information(
        self,
        text_content: str,
    ) -> list[dict[str, Any]]:
        keyword_configs = {
            "CONFIDENTIAL_LABEL": {
                "label": "대외비 표시",
                "severity": "CRITICAL",
                "keywords": [
                    "대외비",
                    "기밀",
                    "confidential",
                    "secret",
                    "내부 전용",
                    "외부 공유 금지",
                ],
            },
            "CREDENTIAL_INFORMATION": {
                "label": "인증정보",
                "severity": "CRITICAL",
                "keywords": [
                    "api key",
                    "apikey",
                    "access token",
                    "secret key",
                    "password",
                    "비밀번호",
                    "인증 토큰",
                ],
            },
            "CONTRACT_INFORMATION": {
                "label": "계약·금액정보",
                "severity": "HIGH",
                "keywords": [
                    "계약 금액",
                    "단가",
                    "견적 금액",
                    "정산 금액",
                    "지급 조건",
                ],
            },
            "INTERNAL_SYSTEM_INFORMATION": {
                "label": "내부 시스템 정보",
                "severity": "HIGH",
                "keywords": [
                    "내부 서버",
                    "운영 서버",
                    "관리자 계정",
                    "데이터베이스 주소",
                    "접속 정보",
                ],
            },
        }

        lowered_text = text_content.lower()
        findings: list[dict[str, Any]] = []

        for finding_type, config in (
            keyword_configs.items()
        ):
            matched_keywords = [
                keyword
                for keyword in config["keywords"]
                if keyword.lower() in lowered_text
            ]

            if matched_keywords:
                findings.append(
                    {
                        "finding_type":
                            finding_type,
                        "label":
                            config["label"],
                        "severity":
                            config["severity"],
                        "matched_keywords":
                            matched_keywords,
                    }
                )

        return findings

    def _calculate_risk_score(
        self,
        privacy_findings: list[dict[str, Any]],
        confidentiality_findings: list[
            dict[str, Any]
        ],
    ) -> int:
        severity_scores = {
            "LOW": 5,
            "MEDIUM": 10,
            "HIGH": 20,
            "CRITICAL": 35,
        }

        all_findings = (
            privacy_findings
            + confidentiality_findings
        )

        score = sum(
            severity_scores.get(
                finding["severity"],
                0,
            )
            for finding in all_findings
        )

        return min(score, 100)

    def _get_risk_level(
        self,
        score: int,
    ) -> str:
        if score >= 70:
            return "CRITICAL"

        if score >= 40:
            return "HIGH"

        if score >= 15:
            return "MEDIUM"

        return "LOW"

    def _make_recommended_actions(
        self,
        privacy_findings: list[dict[str, Any]],
        confidentiality_findings: list[
            dict[str, Any]
        ],
        risk_level: str,
    ) -> list[str]:
        actions: list[str] = []

        if privacy_findings:
            actions.append(
                "개인정보를 마스킹하거나 삭제한 후 "
                "산출물을 다시 등록합니다."
            )

        if confidentiality_findings:
            actions.append(
                "문서 공개 범위와 접근 권한을 "
                "PM 또는 승인자에게 확인합니다."
            )

        if risk_level in {"HIGH", "CRITICAL"}:
            actions.append(
                "자동 등록을 중지하고 담당자의 "
                "수동 검토와 승인을 진행합니다."
            )

        if not actions:
            actions.append(
                "민감정보가 탐지되지 않아 "
                "산출물 등록을 진행할 수 있습니다."
            )

        return actions

    def _mask_sensitive_information(
        self,
        text_content: str,
    ) -> str:
        masked_text = text_content

        replacement_patterns = [
            (
                r"\b\d{6}-?[1-4]\d{6}\b",
                "******-*******",
            ),
            (
                r"\b01[016789]-?"
                r"\d{3,4}-?\d{4}\b",
                "010-****-****",
            ),
            (
                r"\b[A-Za-z0-9._%+-]+"
                r"@[A-Za-z0-9.-]+"
                r"\.[A-Za-z]{2,}\b",
                "***@***.***",
            ),
            (
                r"\b(?:\d{4}[- ]?){3}"
                r"\d{4}\b",
                "****-****-****-****",
            ),
        ]

        for pattern, replacement in (
            replacement_patterns
        ):
            masked_text = re.sub(
                pattern,
                replacement,
                masked_text,
            )

        return masked_text

    def _mask_value(
        self,
        value: str,
    ) -> str:
        if len(value) <= 4:
            return "*" * len(value)

        return (
            value[:2]
            + "*" * (len(value) - 4)
            + value[-2:]
        )