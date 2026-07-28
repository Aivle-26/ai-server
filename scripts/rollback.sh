#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

DEPLOY_DIR="/opt/aipm/ai-server"
VENV_DIR="$DEPLOY_DIR/.venv"
VENV_ROOT="$DEPLOY_DIR/venvs"
BACKUP_ROOT="$DEPLOY_DIR/backups"
SERVICE_NAME="aipm-ai-server.service"
HEALTH_CHECK="$DEPLOY_DIR/scripts/health-check.sh"
LOCK_FILE="/tmp/aipm-ai-deploy.lock"

die() {
  echo "AI rollback aborted: $*" >&2
  exit 1
}

write_revision() {
  local revision="$1"
  local temporary_revision="$DEPLOY_DIR/.REVISION.$$"
  printf '%s\n' "$revision" >"$temporary_revision"
  chmod 0644 "$temporary_revision"
  mv -f "$temporary_revision" "$DEPLOY_DIR/REVISION"
}

restore_revision() {
  local revision_file="$1"
  local revision
  revision="$(tr -d '\r\n' <"$revision_file")"
  if [[ "$revision" == "UNRECORDED" ]]; then
    rm -f "$DEPLOY_DIR/REVISION"
  else
    write_revision "$revision"
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

latest_backup() {
  find "$BACKUP_ROOT" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -printf '%f\n' |
    LC_ALL=C sort -r |
    head -n 1
}

if [[ "$#" -gt 1 ]]; then
  echo "Usage: $0 [backup-directory-name]" >&2
  exit 2
fi

[[ -d "$DEPLOY_DIR" ]] || die "deployment directory not found"
[[ -d "$BACKUP_ROOT" ]] || die "backup directory not found"
[[ -d "$VENV_ROOT" ]] || die "versioned virtual environment directory not found"
[[ -L "$VENV_DIR" ]] || die ".venv must be a symlink before rollback"
[[ -x "$VENV_DIR/bin/python" ]] || die "current virtual environment is invalid"
[[ -x "$HEALTH_CHECK" ]] || die "health-check script is not executable"
sudo -n systemctl is-active --quiet "$SERVICE_NAME" ||
  die "$SERVICE_NAME must be active before rollback"

exec 9>"$LOCK_FILE"
flock -n 9 || die "another AI deployment or rollback is running"

BACKUP_NAME="${1:-$(latest_backup)}"
[[ -n "$BACKUP_NAME" ]] || die "no deployment backup is available"
[[ "$BACKUP_NAME" != */* ]] || die "backup must be specified by directory name"

BACKUP_DIR="$(readlink -f "$BACKUP_ROOT/$BACKUP_NAME")"
case "$BACKUP_DIR" in
  "$BACKUP_ROOT"/*) ;;
  *) die "backup path escaped the backup root" ;;
esac

[[ -d "$BACKUP_DIR/source" ]] || die "backup source is missing"
[[ -d "$BACKUP_DIR/venv" ]] || die "backup virtual environment is missing"
[[ -f "$BACKUP_DIR/REVISION" ]] || die "backup REVISION is missing"
[[ -f "$BACKUP_DIR/requirements.txt" ]] ||
  die "backup requirements snapshot is missing"
[[ -f "$BACKUP_DIR/dependency-freeze.txt" ]] ||
  die "backup dependency snapshot is missing"
[[ -f "$BACKUP_DIR/deployment-metadata.txt" ]] ||
  die "backup metadata is missing"

TARGET_VENV_RELATIVE="$(
  sed -n 's/^VENV_TARGET=//p' "$BACKUP_DIR/deployment-metadata.txt" |
    head -n 1
)"
[[ "$TARGET_VENV_RELATIVE" == venvs/* ]] ||
  die "backup contains an invalid virtual environment target"
if [[ "$TARGET_VENV_RELATIVE" == ../* ||
  "$TARGET_VENV_RELATIVE" == */../* ||
  "$TARGET_VENV_RELATIVE" == */.. ]]; then
  die "backup virtual environment target contains path traversal"
fi
TARGET_VENV="$(readlink -m "$DEPLOY_DIR/$TARGET_VENV_RELATIVE")"
case "$TARGET_VENV" in
  "$VENV_ROOT"/*) ;;
  *) die "rollback virtual environment escaped $VENV_ROOT" ;;
esac

CURRENT_VENV_LINK="$(readlink "$VENV_DIR")"
CURRENT_VENV_TARGET="$(readlink -f "$VENV_DIR")"
if [[ "$CURRENT_VENV_TARGET" == "$TARGET_VENV" ]]; then
  die "the requested backup virtual environment is already active"
fi

if [[ ! -d "$TARGET_VENV" ]]; then
  mkdir -p "$TARGET_VENV"
  cp -al "$BACKUP_DIR/venv/." "$TARGET_VENV/"
fi
[[ -x "$TARGET_VENV/bin/python" ]] ||
  die "restored backup virtual environment is invalid"

(
  cd "$BACKUP_DIR/source"
  "$TARGET_VENV/bin/python" -m pip check
  "$TARGET_VENV/bin/python" -c \
    "import fastapi, langgraph, openai, pydantic, sqlalchemy, uvicorn; from app.main import app; assert app"
)

ROLLBACK_STARTED_AT="$(date -u +%Y%m%dT%H%M%SZ)"
CURRENT_REVISION="UNRECORDED"
if [[ -f "$DEPLOY_DIR/REVISION" ]]; then
  CURRENT_REVISION="$(tr -d '\r\n' <"$DEPLOY_DIR/REVISION")"
fi
CURRENT_REVISION_LABEL="$(printf '%s' "$CURRENT_REVISION" | tr -cd '0-9A-Za-z._-')"
[[ -n "$CURRENT_REVISION_LABEL" ]] || CURRENT_REVISION_LABEL="UNRECORDED"
SAFETY_BACKUP="$BACKUP_ROOT/${ROLLBACK_STARTED_AT}-before-manual-rollback-${CURRENT_REVISION_LABEL:0:12}"

mkdir -p "$SAFETY_BACKUP/source" "$SAFETY_BACKUP/venv"
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
  "$SAFETY_BACKUP/source/"
cp -al "$VENV_DIR/." "$SAFETY_BACKUP/venv/"
cp "$DEPLOY_DIR/requirements.txt" "$SAFETY_BACKUP/requirements.txt"
"$VENV_DIR/bin/python" -m pip freeze --all >"$SAFETY_BACKUP/dependency-freeze.txt"
if [[ -f "$DEPLOY_DIR/REVISION" ]]; then
  cp "$DEPLOY_DIR/REVISION" "$SAFETY_BACKUP/REVISION"
else
  printf 'UNRECORDED\n' >"$SAFETY_BACKUP/REVISION"
fi
cat >"$SAFETY_BACKUP/deployment-metadata.txt" <<METADATA
BACKUP_CREATED_AT=$ROLLBACK_STARTED_AT
FROM_REVISION=$CURRENT_REVISION
TO_REVISION=$(tr -d '\r\n' <"$BACKUP_DIR/REVISION")
SERVICE_NAME=$SERVICE_NAME
VENV_TARGET=${CURRENT_VENV_TARGET#"$DEPLOY_DIR/"}
METADATA

restore_current_release() {
  local reason="$1"
  local restored=0

  echo "Manual rollback failed; restoring the pre-rollback release: $reason" >&2
  set +e
  sudo -n systemctl stop "$SERVICE_NAME"
  sync_source "$SAFETY_BACKUP/source"
  rm -f "$VENV_DIR"
  ln -s "$CURRENT_VENV_LINK" "$VENV_DIR"
  restore_revision "$SAFETY_BACKUP/REVISION"
  sudo -n systemctl start "$SERVICE_NAME"
  if "$HEALTH_CHECK"; then
    restored=1
  fi

  if ((restored)); then
    echo "Pre-rollback release restoration succeeded" >&2
  else
    echo "CRITICAL: pre-rollback release health check failed" >&2
  fi
  exit 1
}

DOWNTIME_STARTED_MS="$(date +%s%3N)"
sudo -n systemctl stop "$SERVICE_NAME"
rm "$VENV_DIR"
ln -s "$TARGET_VENV_RELATIVE" "$VENV_DIR"

if ! sync_source "$BACKUP_DIR/source"; then
  restore_current_release "source restoration failed"
fi
restore_revision "$BACKUP_DIR/REVISION"

if ! sudo -n systemctl start "$SERVICE_NAME"; then
  restore_current_release "systemd start failed"
fi
if ! "$HEALTH_CHECK"; then
  restore_current_release "health check failed"
fi

DOWNTIME_FINISHED_MS="$(date +%s%3N)"
DOWNTIME_MS=$((DOWNTIME_FINISHED_MS - DOWNTIME_STARTED_MS))

echo "AI rollback succeeded"
echo "REVISION=$(tr -d '\r\n' <"$BACKUP_DIR/REVISION")"
echo "BACKUP_DIR=$BACKUP_DIR"
echo "SAFETY_BACKUP=$SAFETY_BACKUP"
echo "AI_DOWNTIME_MS=$DOWNTIME_MS"
