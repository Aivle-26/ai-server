# AI Server Runtime Operations

## Runtime ownership

The AI runtime is isolated to these paths and units:

- `/opt/aipm/ai-server`
- `/etc/aipm/ai-server.env`
- `aipm-ai-server.service`

The legacy `/etc/aipm-ai-test.env` and `aipm-ai-test.service` remain available
until the new service has passed deployment, integration, and reboot checks.
Backend, Nginx, database, S3, and frontend resources are outside this
procedure.

## Live layout

```text
/opt/aipm/ai-server/
|-- app/
|-- .venv -> venvs/<deployment-id>/
|-- venvs/
|-- backups/
|-- scripts/
|   |-- deploy.sh
|   |-- rollback.sh
|   `-- health-check.sh
|-- requirements.txt
`-- REVISION
```

Each deployment creates a new immutable virtual environment under `venvs/`.
Only after dependency installation, tests, imports, and `pip check` succeed
does `.venv` switch to the new environment.

## Deployment

GitHub Actions packages the checked-out commit without secrets, local runtime
data, or `sample_data`, uploads the archive, and invokes:

```bash
bash /opt/aipm/ai-server/scripts/deploy.sh \
  /tmp/aipm-ai-<revision>.tar.gz \
  <revision>
```

The deploy script:

1. validates the archive and Git revision;
2. creates and verifies a release-specific virtual environment;
3. tests the release before touching the live service;
4. snapshots the current source, dependencies, and revision;
5. stops only `aipm-ai-server.service`;
6. switches source and `.venv`, then records `REVISION`;
7. starts the service and runs the loopback health check;
8. restores source, dependencies, and revision together on failure; and
9. keeps the newest three deployment backups by default.

Set `AI_BACKUP_RETENTION` to a value from 1 through 10 when a different
retention count is required.

## Backup contents

Every directory under `/opt/aipm/ai-server/backups` contains:

- `source/`
- `venv/`
- `REVISION`
- `requirements.txt`
- `dependency-freeze.txt`
- `deployment-metadata.txt`

The venv snapshot uses hard links on the same filesystem. Release venvs are
immutable, so the snapshot remains consistent while avoiding a full duplicate
of unchanged dependency files.

## Manual rollback

List backups without exposing environment values:

```bash
find /opt/aipm/ai-server/backups \
  -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
  sort -r
```

Rollback to the newest backup:

```bash
bash /opt/aipm/ai-server/scripts/rollback.sh
```

Rollback to a named backup:

```bash
bash /opt/aipm/ai-server/scripts/rollback.sh <backup-directory-name>
```

Before switching, `rollback.sh` creates another safety backup of the active
release. If the requested rollback fails its health check, the script restores
that pre-rollback source, venv, and revision.

## Health and service checks

```bash
systemctl is-active aipm-ai-server.service
systemctl is-enabled aipm-ai-server.service
/opt/aipm/ai-server/scripts/health-check.sh
cat /opt/aipm/ai-server/REVISION
```

The deployment health URL is fixed to
`http://127.0.0.1:8090/health`. Nginx routes are checked separately and are
not part of the deployment success decision.

## Legacy service boundary

Do not delete or disable the legacy unit or environment file during this
workflow migration. Deployment and rollback scripts never start, restart, or
stop the legacy unit. Because both units bind port 8090, only the common
infrastructure owner may change the legacy unit after the new Actions workflow
and integration checks have passed.
