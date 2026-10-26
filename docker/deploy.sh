#!/usr/bin/env bash
set -euo pipefail
PROJECT=/home/student/ml-prediction-service
COMPOSE="$PROJECT/docker/docker-compose.yml"
# The timer deploys published images; local test overrides must not leak here.
unset ML_APP_IMAGE PREDICTION_IMAGE LOGGER_IMAGE
cd "$PROJECT"
if ! timeout 900s docker compose -f "$COMPOSE" pull prediction-service logger-service alert-receiver; then
    echo "Pull failed; running containers were not replaced" >&2
    exit 1
fi
docker compose -f "$COMPOSE" up -d --no-build --pull never --remove-orphans
for attempt in {1..20}; do
    ready=1
    for container in prediction-service logger-service; do
        health=$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || true)
        if [ "$health" != healthy ]; then ready=0; fi
    done
    if [ "$ready" -eq 1 ]; then
        echo "Deployment successful: prediction-service and logger-service healthy"
        exit 0
    fi
    sleep 3
done
echo "Deployment failed: services did not become healthy" >&2
exit 1
