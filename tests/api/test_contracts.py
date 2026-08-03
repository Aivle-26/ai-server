import unittest

from fastapi.testclient import TestClient

from app.main import app


POST_ENDPOINTS = {
    "/api/v1/planning/documents/extract",
    "/api/v1/planning/wbs/generate",
    "/api/v1/planning/schedules/recommend",
    "/api/v1/planning/resources/recommend",
    "/api/v1/planning/costs/estimate",
    "/api/v1/risk/communication/analyze",
    "/api/v1/risk/impact-assessment",
    "/api/v1/risk/assignee-reassignment",
    "/api/v1/risk/artifact-security",
    "/api/v1/risk/artifact-status",
    "/api/v1/risk/member-delay",
    "/api/v1/risk/schedule-wbs-risk",
    "/api/v1/reports/meeting/analyze",
    "/api/v1/reports/weekly/generate",
    "/api/v1/reports/final/generate",
    "/api/v1/reports/deliverables/rag/query",
}


class ApiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.openapi = app.openapi()

    def test_health_contract(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertEqual(response.json(), {"status": "ok"})

    def test_all_expected_domain_routes_are_registered_as_post(self):
        self.assertTrue(POST_ENDPOINTS.issubset(self.openapi["paths"]))
        for path in POST_ENDPOINTS:
            with self.subTest(path=path):
                self.assertEqual(set(self.openapi["paths"][path]), {"post"})

    def test_empty_requests_are_rejected_with_json_422(self):
        for path in sorted(POST_ENDPOINTS):
            with self.subTest(path=path):
                if path == "/api/v1/planning/documents/extract":
                    response = self.client.post(path, files=[])
                else:
                    response = self.client.post(path, json={})

                self.assertEqual(response.status_code, 422)
                self.assertTrue(
                    response.headers["content-type"].startswith("application/json")
                )
                body = response.json()
                self.assertEqual(body["code"], "VALIDATION_ERROR")
                self.assertEqual(body["request_id"], response.headers["X-Request-ID"])
                self.assertFalse(body["retryable"])
                self.assertIsInstance(body["details"], list)

    def test_domain_routes_reject_get_method(self):
        for path in sorted(POST_ENDPOINTS):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.json()["code"], "METHOD_NOT_ALLOWED")
                self.assertEqual(response.json()["message"], "Method Not Allowed")

    def test_request_id_is_generated_or_propagated(self):
        generated = self.client.get("/health")
        self.assertRegex(generated.headers["X-Request-ID"], r"^[a-f0-9]{32}$")

        supplied = self.client.get(
            "/health",
            headers={"X-Request-ID": "backend-request-123"},
        )
        self.assertEqual(
            supplied.headers["X-Request-ID"],
            "backend-request-123",
        )

        invalid = self.client.get(
            "/health",
            headers={"X-Request-ID": "invalid request id"},
        )
        self.assertNotEqual(
            invalid.headers["X-Request-ID"],
            "invalid request id",
        )

    def test_openapi_uses_common_error_response(self):
        self.assertIn("ErrorResponse", self.openapi["components"]["schemas"])
        for path in POST_ENDPOINTS:
            with self.subTest(path=path):
                operation = self.openapi["paths"][path]["post"]
                for status_code in ("400", "413", "422", "502", "503", "504"):
                    response = operation["responses"][status_code]
                    schema = response["content"]["application/json"]["schema"]
                    self.assertEqual(
                        schema["$ref"],
                        "#/components/schemas/ErrorResponse",
                    )
                    self.assertIn("X-Request-ID", response["headers"])

    def test_response_models_are_declared_for_backend_contract(self):
        expected_response_schemas = {
            "/api/v1/planning/documents/extract": "PlanningDocumentExtractionResponse",
            "/api/v1/planning/wbs/generate": "WBSGenerationResponse",
            "/api/v1/planning/schedules/recommend": "PlanningScheduleResponse",
            "/api/v1/planning/resources/recommend": "PlanningResourceResponse",
            "/api/v1/planning/costs/estimate": "PlanningCostResponse",
            "/api/v1/risk/communication/analyze": "CommunicationRiskResponse",
            "/api/v1/risk/impact-assessment": "ImpactAssessmentResponse",
            "/api/v1/risk/assignee-reassignment": "AssigneeReassignmentResponse",
            "/api/v1/risk/artifact-security": "ArtifactSecurityResponse",
            "/api/v1/risk/artifact-status": "ArtifactStatusResponse",
            "/api/v1/risk/member-delay": "MemberDelayResponse",
            "/api/v1/risk/schedule-wbs-risk": "ScheduleWBSRiskResponse",
            "/api/v1/reports/meeting/analyze": "MeetingAnalysisResponse",
            "/api/v1/reports/weekly/generate": "WeeklyReportResponse",
            "/api/v1/reports/final/generate": "FinalReportResponse",
            "/api/v1/reports/deliverables/rag/query": "DeliverableRagResponse",
        }

        for path, schema_name in expected_response_schemas.items():
            with self.subTest(path=path):
                schema = self.openapi["paths"][path]["post"]["responses"]["200"][
                    "content"
                ]["application/json"]["schema"]
                self.assertEqual(
                    schema["$ref"], f"#/components/schemas/{schema_name}"
                )

    def test_document_endpoint_is_multipart_with_binary_file_array(self):
        operation = self.openapi["paths"][
            "/api/v1/planning/documents/extract"
        ]["post"]
        content = operation["requestBody"]["content"]

        self.assertEqual(set(content), {"multipart/form-data"})
        body_schema = content["multipart/form-data"]["schema"]
        self.assertIn("$ref", body_schema)
        referenced_name = body_schema["$ref"].rsplit("/", 1)[-1]
        referenced = self.openapi["components"]["schemas"][referenced_name]
        file_items = referenced["properties"]["files"]["items"]
        self.assertEqual(file_items["type"], "string")
        self.assertEqual(file_items["format"], "binary")


if __name__ == "__main__":
    unittest.main()
