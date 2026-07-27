import io
import importlib
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.agents.planning_document_graph import PlanningDocumentGraph
from app.main import app
from app.services.planning_document_service import PlanningDocumentService, UploadedDocument
from app.services.planning_llm_extraction_service import (
    DocumentChunkExtraction,
    ExtractedProjectInfo,
    PlanningLLMExtractionService,
)


SAMPLE_TEXT = """프로젝트명: AI 학생 맞춤형 학습지원시스템 구축
프로젝트 목표: 학생별 학습 데이터를 분석해 맞춤형 학습 지원 체계 구축
발주기관: OO대학교
수행 기간: 2026.08.01 ~ 2026.12.31
주요 기능: 대시보드, AI 분석, 관리자 기능, 보고서 생성
주요 산출물: 요구사항 정의서, 설계서, 테스트 결과서
검수 조건: 기능 테스트를 통과해야 한다
보안/개인정보 조건: 개인정보 암호화 및 역할별 접근권한 적용
REQ-001 필수 - 시스템은 학생별 학습 현황 대시보드를 제공해야 한다.
REQ-002 시스템은 개인정보를 저장할 때 암호화해야 한다.
"""


class FakeLLMService:
    def extract(self, chunks, vision_documents, fallback_extractions):
        result = fallback_extractions
        result[0]["project_info"]["project_name"] = "LLM 추출 프로젝트"
        result[0]["requirements"][0]["acceptance_criteria"] = "대시보드 조회 테스트 통과"
        result[0]["requirements"][0]["category"] = "NON_FUNCTIONAL"
        return result, "SUCCEEDED"


class NoApiKeyLLMService:
    def extract(self, chunks, vision_documents, fallback_extractions):
        return fallback_extractions, "SKIPPED_NO_API_KEY"


class FakeVisionLLMService:
    def extract(self, chunks, vision_documents, fallback_extractions):
        document = vision_documents[0]
        return [{
            "project_info": {
                "project_name": "스캔 PDF 프로젝트",
                "project_goal": None,
                "client_organization": None,
                "period_start": None,
                "period_end": None,
                "key_features": [],
                "required_artifacts": [],
                "acceptance_conditions": [],
                "budget_contract_conditions": [],
                "security_privacy_conditions": [],
            },
            "requirements": [{
                "function_name": "문서 조회",
                "requirement_text": "사용자는 스캔 문서를 조회할 수 있어야 한다.",
                "category": "FUNCTIONAL",
                "priority": "UNSPECIFIED",
                "acceptance_criteria": None,
                "due_date": None,
                "deliverable_name": None,
                "security_condition": None,
                "source_document": document.file_name,
                "source_excerpt": "스캔 문서를 조회할 수 있어야 한다.",
            }],
        }], "SUCCEEDED"


class CapturingResponses:
    def __init__(self):
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_parsed=DocumentChunkExtraction(
            project_info=ExtractedProjectInfo(project_name="비전 분석 프로젝트"),
            requirements=[],
        ))


class PlanningDocumentGraphTest(unittest.TestCase):
    def setUp(self):
        self.upload = UploadedDocument(
            file_name="RFP.txt",
            content_type="text/plain",
            content=SAMPLE_TEXT.encode("utf-8"),
        )

    def test_fallback_extracts_project_and_requirements(self):
        graph = PlanningDocumentGraph(llm_service=NoApiKeyLLMService())
        result = graph.invoke([self.upload])
        self.assertEqual(result["project_info"]["project_name"], "AI 학생 맞춤형 학습지원시스템 구축")
        self.assertEqual(result["project_info"]["client_organization"], "OO대학교")
        self.assertEqual(result["project_info"]["period_start"], "2026-08-01")
        self.assertEqual(result["project_info"]["required_artifacts"], [
            {
                "artifact_type": "REQUIREMENTS_DEFINITION",
                "artifact_name": "요구사항 정의서",
                "required_version": "1.0",
            },
            {
                "artifact_type": "TEST_RESULTS",
                "artifact_name": "테스트 결과서",
                "required_version": "1.0",
            },
        ])
        self.assertEqual(len(result["requirement_candidates"]), 3)
        self.assertEqual(result["requirement_candidates"][1]["priority"], "HIGH")
        self.assertEqual(
            [requirement["category"] for requirement in result["requirement_candidates"]],
            ["PROJECT_MANAGEMENT", "FUNCTIONAL", "SECURITY"],
        )
        self.assertEqual(result["llm_status"], "SKIPPED_NO_API_KEY")

    def test_graph_uses_structured_llm_result(self):
        graph = PlanningDocumentGraph(llm_service=FakeLLMService())
        result = graph.invoke([self.upload])
        self.assertEqual(result["project_info"]["project_name"], "LLM 추출 프로젝트")
        self.assertEqual(result["llm_status"], "SUCCEEDED")
        self.assertEqual(result["requirement_candidates"][0]["category"], "NON_FUNCTIONAL")
        self.assertEqual(
            result["requirement_candidates"][0]["acceptance_criteria"],
            "대시보드 조회 테스트 통과",
        )

    def test_hwpx_text_is_supported(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "Contents/section0.xml",
                "<root><p>프로젝트명: HWPX 사업</p><p>시스템은 검색 기능을 제공해야 한다.</p></root>",
            )
        parsed = PlanningDocumentService().parse_documents([
            UploadedDocument("proposal.hwpx", "application/octet-stream", buffer.getvalue())
        ])
        self.assertIn("HWPX 사업", parsed[0].text)

    def test_scanned_pdf_is_routed_to_vision(self):
        buffer = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.write(buffer)
        upload = UploadedDocument(
            file_name="scanned-rfp.pdf",
            content_type="application/pdf",
            content=buffer.getvalue(),
        )

        graph = PlanningDocumentGraph(llm_service=FakeVisionLLMService())
        result = graph.invoke([upload])

        self.assertEqual(result["documents"][0]["processing_mode"], "PDF_VISION")
        self.assertEqual(result["documents"][0]["character_count"], 0)
        self.assertEqual(result["project_info"]["project_name"], "스캔 PDF 프로젝트")
        self.assertEqual(result["requirement_candidates"][0]["source_document"], "scanned-rfp.pdf")
        self.assertEqual(result["requirement_candidates"][0]["category"], "FUNCTIONAL")

    def test_fallback_classifies_all_requirement_categories(self):
        service = PlanningDocumentService()
        examples = {
            "FUNCTIONAL": "시스템은 보고서 조회 기능을 제공해야 한다.",
            "NON_FUNCTIONAL": "시스템 응답시간은 2초 이내여야 한다.",
            "SECURITY": "개인정보는 암호화하여 저장해야 한다.",
            "DATA": "기존 데이터를 신규 데이터베이스로 이관해야 한다.",
            "INTERFACE": "외부 시스템 API와 연계해야 한다.",
            "OPERATION": "운영 모니터링 기능을 제공해야 한다.",
            "PROJECT_MANAGEMENT": "최종 산출물을 검수 전에 제출해야 한다.",
            "UNSPECIFIED": "기타 참고 내용입니다.",
        }
        for expected, text in examples.items():
            with self.subTest(category=expected):
                self.assertEqual(service._category(text), expected)

    def test_fallback_extracts_supported_artifact_types(self):
        service = PlanningDocumentService()
        text = (
            "주요 산출물: RFP, 제안서, 요구사항 정의서, 기능 명세서, WBS, ERD, "
            "회의록, 테스트 결과서, 주간 보고서, 최종 보고서, UI 설계서"
        )
        artifacts = service._artifact_list(text, ("주요 산출물",))
        self.assertEqual([artifact["artifact_type"] for artifact in artifacts], [
            "RFP",
            "PROPOSAL",
            "REQUIREMENTS_DEFINITION",
            "FUNCTION_SPECIFICATION",
            "WBS",
            "ERD",
            "MEETING_MINUTES",
            "TEST_RESULTS",
            "WEEKLY_REPORT",
            "FINAL_REPORT",
            "UI_DESIGN",
        ])
        self.assertTrue(all(
            artifact["required_version"] == "1.0" for artifact in artifacts
        ))

    def test_condition_lists_are_normalized_to_short_phrases(self):
        service = PlanningDocumentService()
        fallback = service.fallback_extract({
            "source_document": "RFP.txt",
            "text": "\n".join((
                "검수 조건: 산출물을 제출한 후 검수해야 한다; 기능 테스트를 통과해야 한다.",
                "예산/계약 조건: 총 사업비는 5억원으로 한다; 검수 완료 후 잔금을 지급한다.",
                "보안/개인정보 조건: 개인정보를 암호화해야 한다; 역할별 접근권한을 적용해야 한다.",
            )),
        })
        project_info = fallback["project_info"]
        self.assertEqual(project_info["acceptance_conditions"], [
            "산출물 제출 후 검수",
            "기능 테스트 통과",
        ])
        self.assertEqual(project_info["budget_contract_conditions"], [
            "총 사업비 5억원",
            "검수 완료 후 잔금 지급",
        ])
        self.assertEqual(project_info["security_privacy_conditions"], [
            "개인정보 암호화",
            "역할별 접근권한 적용",
        ])

        consolidated = service.consolidate([{
            "project_info": {
                "acceptance_conditions": ["기능 테스트를 통과해야 한다."],
                "budget_contract_conditions": ["검수 완료 후 잔금을 지급한다."],
                "security_privacy_conditions": ["개인정보를 암호화해야 한다."],
            },
            "requirements": [],
        }])
        self.assertEqual(consolidated["project_info"]["acceptance_conditions"], [
            "기능 테스트 통과",
        ])
        self.assertEqual(consolidated["project_info"]["budget_contract_conditions"], [
            "검수 완료 후 잔금 지급",
        ])
        self.assertEqual(consolidated["project_info"]["security_privacy_conditions"], [
            "개인정보 암호화",
        ])

    def test_vision_request_sends_original_pdf_as_structured_file_input(self):
        responses = CapturingResponses()
        client = SimpleNamespace(responses=responses)
        document = SimpleNamespace(file_name="scan.pdf", content=b"%PDF-test")

        result = PlanningLLMExtractionService()._extract_pdf_with_vision(client, document)

        file_input = responses.request["input"][0]["content"][0]
        self.assertEqual(file_input["type"], "input_file")
        self.assertEqual(file_input["filename"], "scan.pdf")
        self.assertTrue(file_input["file_data"].startswith("data:application/pdf;base64,"))
        self.assertIn(file_input["detail"], {"auto", "low", "high"})
        self.assertIs(responses.request["text_format"], DocumentChunkExtraction)
        self.assertFalse(responses.request["store"])
        self.assertEqual(result["project_info"]["project_name"], "비전 분석 프로젝트")

    def test_fastapi_accepts_uploaded_document(self):
        test_graph = PlanningDocumentGraph(llm_service=NoApiKeyLLMService())
        with patch.object(importlib.import_module("app.main"), "planning_document_graph", test_graph):
            response = TestClient(app).post(
                "/api/v1/planning/documents/extract",
                files=[("files", ("RFP.txt", SAMPLE_TEXT.encode("utf-8"), "text/plain"))],
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_info"]["project_name"], "AI 학생 맞춤형 학습지원시스템 구축")
        self.assertGreaterEqual(len(body["requirement_candidates"]), 2)

    def test_fastapi_rejects_unsupported_file(self):
        response = TestClient(app).post(
            "/api/v1/planning/documents/extract",
            files=[("files", ("RFP.exe", b"not a document", "application/octet-stream"))],
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("지원하지 않는 파일 형식", response.json()["detail"])

    def test_openapi_exposes_files_as_binary_uploads(self):
        schema = app.openapi()
        self.assertEqual(schema["info"]["title"], "AI Project Data Platform")
        self.assertEqual(
            schema["paths"]["/api/v1/risk/communication/analyze"]["post"]["summary"],
            "프로젝트 커뮤니케이션 위험 분석",
        )
        self.assertEqual(
            schema["paths"]["/api/v1/planning/documents/extract"]["post"]["summary"],
            "프로젝트 초기 문서 정보 및 요구사항 추출",
        )
        request_schema = schema["components"]["schemas"][
            "Body_extract_planning_documents_api_v1_planning_documents_extract_post"
        ]
        file_items = request_schema["properties"]["files"]["items"]
        self.assertEqual(file_items, {"type": "string", "format": "binary"})
        category_schema = schema["components"]["schemas"]["RequirementCandidate"][
            "properties"
        ]["category"]
        self.assertEqual(category_schema["enum"], [
            "FUNCTIONAL",
            "NON_FUNCTIONAL",
            "SECURITY",
            "DATA",
            "INTERFACE",
            "OPERATION",
            "PROJECT_MANAGEMENT",
            "UNSPECIFIED",
        ])
        project_properties = schema["components"]["schemas"]["ProjectBasicInfo"][
            "properties"
        ]
        self.assertIn("required_artifacts", project_properties)
        self.assertNotIn("deliverables", project_properties)
        artifact_type_schema = schema["components"]["schemas"]["RequiredArtifact"][
            "properties"
        ]["artifact_type"]
        self.assertEqual(artifact_type_schema["enum"], [
            "RFP",
            "PROPOSAL",
            "REQUIREMENTS_DEFINITION",
            "FUNCTION_SPECIFICATION",
            "WBS",
            "ERD",
            "MEETING_MINUTES",
            "TEST_RESULTS",
            "WEEKLY_REPORT",
            "FINAL_REPORT",
            "UI_DESIGN",
        ])


if __name__ == "__main__":
    unittest.main()
