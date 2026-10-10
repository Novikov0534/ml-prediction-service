#!/usr/bin/env bash
set -euo pipefail

IMAGE=ghcr.io/novikov0534/ml-prediction-service/ml-app:latest
COMPOSE=/home/student/ml-prediction-service/docker/docker-compose.yml

current=$(docker inspect --format '{{.Image}}' ml-app 2>/dev/null || true)
docker pull "$IMAGE"
available=$(docker image inspect --format '{{.Id}}' "$IMAGE")

if [ "$current" = "$available" ]; then
    echo "Image unchanged; deployment not needed"
    exit 0
fi

docker-compose -f "$COMPOSE" down
docker-compose -f "$COMPOSE" up -d

for attempt in {1..15}; do
    if curl -fsS http://127.0.0.1:5000/health >/dev/null; then
        echo "Deployment successful: $available"
        exit 0
    fi
    sleep 2
done

echo "Deployment failed: health check did not pass" >&2
exit 1
