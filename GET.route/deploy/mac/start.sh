#!/bin/bash
# GET.route on a Mac mini: WORKERS Waze processes (run.py) on BASE_PORT,
# BASE_PORT+1, ... and the pool dispatcher (pool_server.py) on POOL_PORT in
# front of them, all on this Mac only (127.0.0.1); cloudflared publishes the
# dispatcher. A process that stops is started again after 5 s. Logs go to
# logs/ next to this script. Run it from launchd (com.getride.getroute.plist)
# so it starts at login and comes back if it stops.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$(cd "$HERE/../.." && pwd)"           # the GET.route folder
cd "$HERE"
[ -f .env ] || { echo "No .env next to start.sh (copy .env.example)"; exit 1; }
set -a; . ./.env; set +a
: "${ROUTE_API_KEY:?Set ROUTE_API_KEY in .env}"
WORKERS="${WORKERS:-4}"; POOL_PORT="${POOL_PORT:-8100}"; BASE_PORT="${BASE_PORT:-8101}"
PY="$APP/.venv/bin/python"
[ -x "$PY" ] || { echo "No $PY: create the venv first (see README.md)"; exit 1; }
mkdir -p "$HERE/logs"
export HOST=127.0.0.1

keep_running() {   # name, then the command
  local name="$1"; shift
  while true; do
    echo "$(date '+%F %T') starting $name" >> "$HERE/logs/$name.log"
    "$@" >> "$HERE/logs/$name.log" 2>&1
    echo "$(date '+%F %T') $name stopped ($?); again in 5 s" >> "$HERE/logs/$name.log"
    sleep 5
  done
}

servers=""
for i in $(seq 1 "$WORKERS"); do
  port=$((BASE_PORT + i - 1))
  servers="${servers:+$servers,}http://127.0.0.1:$port"
  (cd "$APP" && PORT="$port" keep_running "worker-$(printf %02d "$i")" "$PY" run.py) &
done
sleep 2
(cd "$APP" && PORT="$POOL_PORT" POOL_SERVERS="$servers" keep_running pool "$PY" pool_server.py) &

trap 'kill 0' EXIT TERM INT
wait
