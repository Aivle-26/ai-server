# Organization chart image generation

The planning resource domain exposes two independent operations:

- `POST /api/v1/planning/resources/recommend` keeps the existing assignment recommendation contract.
- `POST /api/v1/planning/resources/organization-chart/generate` runs the same resource graph, builds the validated `OrganizationView`, and renders a JPG.

The generation request wraps `planning_request` and optional `organization_metadata`. `project_name` and each member's `member_name` are optional presentation fields on the planning request. The caller must supply real names; the AI server does not invent names, a project manager, team leaders, reporting lines, or collaboration links.

The response contains the organization JSON and a transfer-only Base64 JPG. The Base64 value is not persisted by the AI server. Figma, browser automation, and Figma tokens are intentionally outside this feature.

```json
{
  "planning_request": {
    "project_id": 1,
    "project_name": "AIPM Project",
    "wbs_tasks": [
      {
        "wbs_id": 10,
        "wbs_name": "Backend API",
        "description": "Implement the API",
        "start_date": "2026-08-05",
        "end_date": "2026-08-12"
      }
    ],
    "project_members": [
      {
        "project_member_id": 1,
        "member_name": "Project Manager",
        "roles": ["PM"],
        "skills": [],
        "allocations": []
      }
    ]
  },
  "organization_metadata": {
    "project_manager_member_id": 1,
    "teams": []
  }
}
```

The response contains `organization`, `file_name`, `content_type`,
`image_base64`, `width`, and `height`. Requests must satisfy the existing
planning resource schema.

## Korean font

The renderer requires a Korean-capable Noto Sans CJK font. On Amazon Linux, install the appropriate Noto CJK package from the configured OS repositories, verify the installed file, and set:

```text
ORG_CHART_FONT_PATH=/absolute/path/to/NotoSansCJK-Regular.ttc
```

Add only the variable name and verified path to `/etc/aipm/ai-server.env`; do not commit the environment file. If the variable is absent, the renderer checks a small set of standard Linux Noto CJK locations. Missing or unreadable fonts produce an explicit `503` instead of a broken image.

## Local verification

```bash
python -m unittest tests.domains.planning_resources.test_organization_chart -v
python -m unittest discover -v
python -m compileall -q app tests
```

Rendering is bounded by member, pixel, width, and height limits. Generated images use a white background and JPEG quality 92.
