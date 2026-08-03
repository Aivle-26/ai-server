# Planning Document E2E Stub

This FastAPI application is test-only. It is not imported by `app/main.py` and
does not create an OpenAI client.

Run it on loopback port 8091:

```bash
python -m uvicorn tests.e2e_stub.app:app \
  --host 127.0.0.1 \
  --port 8091 \
  --workers 1
```

The stub implements the production planning-document contract:

- `GET /health`
- `POST /api/v1/planning/documents/extract`
- multipart field `files`
- `PlanningDocumentExtractionResponse`

Each valid request returns exactly three deterministic requirements. Missing
multipart data and empty files return HTTP 422.
