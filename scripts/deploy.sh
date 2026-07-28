#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

DEPLOY_DIR="/opt/aipm/ai-server"
VENV_DIR="$DEPLOY_DIR/.venv"
VENV_ROOT="$DEPLOY_DIR/venvs"
BACKUP_ROOT="$DEPLOY_DIR/backups"
SERVICE_NAME="aipm-ai-server.service"
ENV_FILE="/etc/aipm/ai-server.env"
PYTHON_BIN="${AI_PYTHON_BIN:-/usr/bin/python3.11}"
BACKUP_RETENTION="${AI_BACKUP_RETENTION:-3}"
HEALTH_CHECK="$DEPLOY_DIR/scripts/health-check.sh"
LOCK_FILE="/tmp/aipm-ai-deploy.lock"

usage() {
  echo "Usage: $0 <source-archive.tar.gz> <git-revision>" >&2
}

die() {
  echo "AI deployment aborted: $*" >&2
  exit 1
}

safe_remove_tree() {
  local path="$1"
  case "$path" in
    "$VENV_ROOT"/* | /tmp/aipm-ai-release-*)
      rm -rf -- "$path"
      ;;
    *)
      die "refusing to remove unexpected path: $path"
      ;;
  esac
}

write_revision() {
  local revision="$1"
  local temporary_revision="$DEPLOY_DIR/.REVISION.$$"
  printf '%s\n' "$revision" >"$temporary_revision"
  chmod 0644 "$temporary_revision"
  mv -f "$temporary_revision" "$DEPLOY_DIR/REVISION"
}

restore_revision() {
  local backup_revision_file="$1"
  local backup_revision
  backup_revision="$(tr -d '\r\n' <"$backup_revision_file")"
  if [[ "$backup_revision" == "UNRECORDED" ]]; then
    rm -f "$DEPLOY_DIR/REVISION"
  else
    write_revision "$backup_revision"
  fi
}

sync_source() {
  local source_dir="$1"
  rsync \
    --archive \
    --delete \
    --exclude='.venv' \
    --exclude='.venv/' \
    --exclude='venvs/' \
    --exclude='backups/' \
    --exclude='REVISION' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='.env' \
    --exclude='.env.*' \
    "$source_dir/" \
    "$DEPLOY_DIR/"
}

prune_backups() {
  local -a backup_names=()
  local index

  mapfile -t backup_names < <(
    find "$BACKUP_ROOT" \
      -mindepth 1 \
      -maxdepth 1 \
      -type d \
      -printf '%f\n' |
      LC_ALL=C sort -r
  )

  for ((index = BACKUP_RETENTION; index < ${#backup_names[@]}; index += 1)); do
    if [[ "${backup_names[$index]}" == */* || -z "${backup_names[$index]}" ]]; then
      die "invalid backup directory name: ${backup_names[$index]}"
    fi
    rm -rf -- "$BACKUP_ROOT/${backup_names[$index]}"
  done
}

if [[ "$#" -ne 2 ]]; then
  usage
  exit 2
fi

ARCHIVE_PATH="$(readlink -f "$1")"
REVISION="$2"

[[ "$REVISION" =~ ^[0-9a-fA-F]{7,40}$ ]] ||
  die "revision must be a 7-40 character hexadecimal Git SHA"
[[ "$BACKUP_RETENTION" =~ ^[1-9][0-9]*$ ]] ||
  die "AI_BACKUP_RETENTION must be a positive integer"
((BACKUP_RETENTION <= 10)) ||
  die "AI_BACKUP_RETENTION must not exceed 10"

[[ -f "$ARCHIVE_PATH" ]] || die "source archive not found"
[[ -d "$DEPLOY_DIR" ]] || die "deployment directory not found"
[[ -x "$VENV_DIR/bin/python" ]] || die "current virtual environment is invalid"
[[ -x "$PYTHON_BIN" ]] || die "Python 3.11 executable not found"
[[ -x "$HEALTH_CHECK" ]] || die "health-check script is not executable"
sudo -n test -f "$ENV_FILE" || die "AI environment file not found"
sudo -n systemctl is-active --quiet "$SERVICE_NAME" ||
  die "$SERVICE_NAME must be active before deployment"
sudo -n systemctl is-enabled --quiet "$SERVICE_NAME" ||
  die "$SERVICE_NAME must be enabled before deployment"

for command_name in curl flock rsync tar; do
  command -v "$command_name" >/dev/null ||
    die "required command not found: $command_name"
done

exec 9>"$LOCK_FILE"
flock -n 9 || die "another AI deployment or rollback is running"

DEPLOYED_AT="$(date -u +%Y%m%dT%H%M%SZ)"
REVISION_SHORT="${REVISION:0:12}"
CURRENT_REVISION="UNRECORDED"
if [[ -f "$DEPLOY_DIR/REVISION" ]]; then
  CURRENT_REVISION="$(tr -d '\r\n' <"$DEPLOY_DIR/REVISION")"
fi
CURRENT_REVISION_LABEL="$(printf '%s' "$CURRENT_REVISION" | tr -cd '0-9A-Za-z._-')"
[[ -n "$CURRENT_REVISION_LABEL" ]] || CURRENT_REVISION_LABEL="UNRECORDED"

DEPLOYMENT_ID="${DEPLOYED_AT}-${REVISION_SHORT}"
RELEASE_DIR="$(mktemp -d "/tmp/aipm-ai-release-${REVISION_SHORT}.XXXXXX")"
CANDIDATE_VENV="$VENV_ROOT/$DEPLOYMENT_ID"
BACKUP_DIR="$BACKUP_ROOT/${DEPLOYED_AT}-from-${CURRENT_REVISION_LABEL:0:12}-to-${REVISION_SHORT}"
PREVIOUS_VENV_TARGET=""
PREVIOUS_VENV_LINK=""
PREVIOUS_VENV_WAS_DIRECTORY=0

cleanup() {
  local active_venv_target=""
  if [[ -L "$VENV_DIR" ]]; then
    active_venv_target="$(readlink -f "$VENV_DIR" || true)"
  fi

  if [[ -d "$RELEASE_DIR" ]]; then
    safe_remove_tree "$RELEASE_DIR"
  fi
  if [[ -d "$CANDIDATE_VENV" && "$active_venv_target" != "$CANDIDATE_VENV" ]]; then
    safe_remove_tree "$CANDIDATE_VENV"
  fi
  case "$ARCHIVE_PATH" in
    /tmp/aipm-ai-*.tar.gz)
      rm -f -- "$ARCHIVE_PATH"
      ;;
  esac
}
trap cleanup EXIT

while IFS= read -r archive_entry; do
  archive_entry="${archive_entry#./}"
  [[ -n "$archive_entry" ]] || continue

  if [[ "$archive_entry" == /* ||
    "$archive_entry" == ".." ||
    "$archive_entry" == ../* ||
    "$archive_entry" == */../* ||
    "$archive_entry" == */.. ]]; then
    die "archive contains an unsafe path"
  fi

  if [[ "$archive_entry" == "sample_data" ||
    "$archive_entry" == sample_data/* ]]; then
    die "sample_data must not be present in an operating archive"
  fi
done < <(tar -tzf "$ARCHIVE_PATH")

tar \
  --extract \
  --gzip \
  --file "$ARCHIVE_PATH" \
  --directory "$RELEASE_DIR" \
  --no-same-owner \
  --no-same-permissions

[[ -f "$RELEASE_DIR/app/main.py" ]] || die "archive is missing app/main.py"
[[ -f "$RELEASE_DIR/requirements.txt" ]] ||
  die "archive is missing requirements.txt"
[[ -f "$RELEASE_DIR/scripts/deploy.sh" ]] ||
  die "archive is missing scripts/deploy.sh"
[[ -f "$RELEASE_DIR/scripts/rollback.sh" ]] ||
  die "archive is missing scripts/rollback.sh"
[[ -f "$RELEASE_DIR/scripts/health-check.sh" ]] ||
  die "archive is missing scripts/health-check.sh"

mkdir -p "$VENV_ROOT" "$BACKUP_ROOT"
chmod 0750 "$VENV_ROOT" "$BACKUP_ROOT"
[[ ! -e "$CANDIDATE_VENV" ]] ||
  die "candidate virtual environment already exists"

"$PYTHON_BIN" -m venv "$CANDIDATE_VENV"
"$CANDIDATE_VENV/bin/python" -m pip install \
  --disable-pip-version-check \
  -r "$RELEASE_DIR/requirements.txt"

(
  cd "$RELEASE_DIR"
  "$CANDIDATE_VENV/bin/python" -m unittest discover -v
  "$CANDIDATE_VENV/bin/python" -m compileall -q app tests
  "$CANDIDATE_VENV/bin/python" -m pip check
  "$CANDIDATE_VENV/bin/python" -c \
    "import fastapi, langgraph, openai, pydantic, sqlalchemy, uvicorn; from app.main import app; assert app"
)

rm -rf \
  "$RELEASE_DIR/.git" \
  "$RELEASE_DIR/.github" \
  "$RELEASE_DIR/deploy" \
  "$RELEASE_DIR/docs" \
  "$RELEASE_DIR/sample_data" \
  "$RELEASE_DIR/tests"
rm -f "$RELEASE_DIR/.env" "$RELEASE_DIR"/.env.*
find "$RELEASE_DIR" \
  -type d \
  -name __pycache__ \
  -prune \
  -exec rm -rf -- {} +
find "$RELEASE_DIR" \
  -type f \
  \( -name '*.pyc' -o -name '*.pyo' \) \
  -delete
chmod 0750 \
  "$RELEASE_DIR/scripts/deploy.sh" \
  "$RELEASE_DIR/scripts/rollback.sh" \
  "$RELEASE_DIR/scripts/health-check.sh"

if [[ -L "$VENV_DIR" ]]; then
  PREVIOUS_VENV_LINK="$(readlink "$VENV_DIR")"
  PREVIOUS_VENV_TARGET="$(readlink -f "$VENV_DIR")"
  case "$PREVIOUS_VENV_TARGET" in
    "$VENV_ROOT"/*) ;;
    *) die "current .venv symlink points outside $VENV_ROOT" ;;
  esac
else
  PREVIOUS_VENV_WAS_DIRECTORY=1
  PREVIOUS_VENV_TARGET="$VENV_ROOT/legacy-${DEPLOYED_AT}-${CURRENT_REVISION_LABEL:0:12}"
  [[ ! -e "$PREVIOUS_VENV_TARGET" ]] ||
    die "legacy virtual environment target already exists"
fi

mkdir -p "$BACKUP_DIR/source" "$BACKUP_DIR/venv"
rsync \
  --archive \
  --delete \
  --exclude='.venv' \
  --exclude='.venv/' \
  --exclude='venvs/' \
  --exclude='backups/' \
  --exclude='REVISION' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='.env' \
  --exclude='.env.*' \
  "$DEPLOY_DIR/" \
  "$BACKUP_DIR/source/"
cp -al "$VENV_DIR/." "$BACKUP_DIR/venv/"
[[ -x "$BACKUP_DIR/venv/bin/python" ]] ||
  die "virtual environment backup is invalid"
cp "$DEPLOY_DIR/requirements.txt" "$BACKUP_DIR/requirements.txt"
"$VENV_DIR/bin/python" -m pip freeze --all >"$BACKUP_DIR/dependency-freeze.txt"
if [[ -f "$DEPLOY_DIR/REVISION" ]]; then
  cp "$DEPLOY_DIR/REVISION" "$BACKUP_DIR/REVISION"
else
  printf 'UNRECORDED\n' >"$BACKUP_DIR/REVISION"
fi
cat >"$BACKUP_DIR/deployment-metadata.txt" <<METADATA
BACKUP_CREATED_AT=$DEPLOYED_AT
FROM_REVISION=$CURRENT_REVISION
TO_REVISION=$REVISION
SERVICE_NAME=$SERVICE_NAME
VENV_TARGET=${PREVIOUS_VENV_TARGET#"$DEPLOY_DIR/"}
METADATA
chmod 0640 \
  "$BACKUP_DIR/REVISION" \
  "$BACKUP_DIR/requirements.txt" \
  "$BACKUP_DIR/dependency-freeze.txt" \
  "$BACKUP_DIR/deployment-metadata.txt"

rollback_failed_deployment() {
  local reason="$1"
  local rollback_healthy=0

  echo "AI deployment failed; restoring source and dependencies: $reason" >&2
  set +e
  sudo -n systemctl stop "$SERVICE_NAME"
  sync_source "$BACKUP_DIR/source"
  rm -f "$VENV_DIR"

  if ((PREVIOUS_VENV_WAS_DIRECTORY)); then
    if [[ -d "$PREVIOUS_VENV_TARGET" ]]; then
      mv "$PREVIOUS_VENV_TARGET" "$VENV_DIR"
    fi
  else
    ln -s "$PREVIOUS_VENV_LINK" "$VENV_DIR"
  fi

  restore_revision "$BACKUP_DIR/REVISION"
  sudo -n systemctl start "$SERVICE_NAME"
  if "$HEALTH_CHECK"; then
    rollback_healthy=1
  fi

  if [[ -d "$CANDIDATE_VENV" ]]; then
    safe_remove_tree "$CANDIDATE_VENV"
  fi

  if ((rollback_healthy)); then
    echo "AI rollback succeeded: $CURRENT_REVISION" >&2
  else
    echo "CRITICAL: AI rollback health check failed" >&2
  fi
  exit 1
}

DOWNTIME_STARTED_MS="$(date +%s%3N)"
sudo -n systemctl stop "$SERVICE_NAME"

if ((PREVIOUS_VENV_WAS_DIRECTORY)); then
  mv "$VENV_DIR" "$PREVIOUS_VENV_TARGET"
else
  rm "$VENV_DIR"
fi
ln -s "venvs/$DEPLOYMENT_ID" "$VENV_DIR"

if ! sync_source "$RELEASE_DIR"; then
  rollback_failed_deployment "source synchronization failed"
fi
write_revision "$REVISION"

if ! sudo -n systemctl start "$SERVICE_NAME"; then
  rollback_failed_deployment "systemd start failed"
fi
if ! "$HEALTH_CHECK"; then
  rollback_failed_deployment "health check failed"
fi

DOWNTIME_FINISHED_MS="$(date +%s%3N)"
DOWNTIME_MS=$((DOWNTIME_FINISHED_MS - DOWNTIME_STARTED_MS))

if [[ -d "$PREVIOUS_VENV_TARGET" ]]; then
  safe_remove_tree "$PREVIOUS_VENV_TARGET"
fi
prune_backups

echo "AI deployment succeeded"
echo "REVISION=$REVISION"
echo "BACKUP_DIR=$BACKUP_DIR"
echo "AI_DOWNTIME_MS=$DOWNTIME_MS"
