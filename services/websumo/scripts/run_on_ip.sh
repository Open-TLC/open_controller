#!/usr/bin/env bash
#
# Run the WebSUMO viewer container against a NATS server on another machine.
#
#   services/websumo/scripts/run_on_ip.sh HOST [PORT]
#
#   HOST  address of the machine running NATS (and Open Controller)
#   PORT  NATS port on that machine (default: 4222)
#
# Builds the image from services/websumo/docker/Dockerfile if it does not
# exist yet, then runs it in the foreground. Open http://localhost:8775 and
# stop with Ctrl-C.

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 HOST [PORT]" >&2
    exit 1
fi

HOST="$1"
PORT="${2:-4222}"
IMAGE=websumo
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Building the $IMAGE image…"
    docker build -t "$IMAGE" -f "$REPO_ROOT/services/websumo/docker/Dockerfile" "$REPO_ROOT"
fi

echo "WebSUMO → NATS at nats://$HOST:$PORT"
echo "Open http://localhost:8775 (Ctrl-C to stop)"
exec docker run --rm -it \
    --name websumo_remote \
    -p 8775:8775 \
    -e NATS_URL="nats://$HOST:$PORT" \
    -e SCENARIOS_DIR=/app/scenarios-empty \
    "$IMAGE"
