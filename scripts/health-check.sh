#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="http://127.0.0.1:8090/health"
HEALTH_RETRIES="${AI_HEALTH_RETRIES:-30}"
HEALTH_SLEEP_SECONDS="${AI_HEALTH_SLEEP_SECONDS:-2}"

if [[ ! "$HEALTH_RETRIES" =~ ^[1-9][0-9]*$ ]]; then
  echo "AI_HEALTH_RETRIES must be a positive integer" >&2
  exit 2
fi

if [[ ! "$HEALTH_SLEEP_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "AI_HEALTH_SLEEP_SECONDS must be a non-negative integer" >&2
  exit 2
fi

for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt += 1)); do
  if curl \
    --fail \
    --silent \
    --show-error \
    --connect-timeout 2 \
    --max-time 5 \
    --output /dev/null \
    "$HEALTH_URL"; then
    echo "AI health check succeeded: $HEALTH_URL"
    exit 0
  fi

  echo "AI health check attempt ${attempt}/${HEALTH_RETRIES} failed" >&2
  if ((attempt < HEALTH_RETRIES)); then
    sleep "$HEALTH_SLEEP_SECONDS"
  fi
done

echo "AI health check failed: $HEALTH_URL" >&2
exit 1
