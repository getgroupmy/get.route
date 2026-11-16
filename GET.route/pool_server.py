"""The pool dispatcher: one front door for all the GET.route containers on
the NAS. GET.ride's Fare AI lists it as a single Waze server
(https://route.getride.my); it hands each query to a container by the rules
in pool.py (container 1 until its 23rd query of the minute, then the next;
the next one warmed at the 10th).

    POOL_SERVERS=http://get-route-01:8000,http://get-route-02:8000 python pool_server.py

    POOL_SERVERS     the containers, in order (required)
    ROUTE_API_KEY    the key callers must send in X-Route-Key; it is also sent
                     to the containers, which use the same one
    POOL_SWITCH_AT   queries per container per minute before the next (23)
    POOL_WARM_AT     query of the minute that warms the next container (10)
    POOL_REST_SECONDS how long a failing container is skipped (60)
    POOL_KEEP_WARM   how many containers (the first ones) to keep Chrome open
                     in between fares (1; 0 = off)
    POOL_KEEP_WARM_SECONDS how often they are asked (240; under the
                     containers' 600 idle seconds, so Chrome never closes)
    PORT             port to listen on (8000)

A query a container could not serve (no answer, 5xx, refused key) is tried
on the next one; Waze's own 400 / 404 answers are passed back as they are.
/health is open; with the key it adds `waze` (when the pool last served a
query, and when one last failed on every container), which GET.ride's
minute-by-minute check reads, and `containers` (each one's load and state).
"""
import datetime
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request

import bottle
from cheroot import wsgi

from pool import Pool

KEEP_WARM_MIN, KEEP_WARM_MAX = 30, 540   # under the containers' BROWSER_IDLE (600 s)
FORWARD_TIMEOUT = 75      # a cold container opens Chrome (20-40 s) before it answers
WARM_TIMEOUT = 5


def _env_int(name, default):
    return int(os.environ.get(name) or default)


KEY = os.environ.get("ROUTE_API_KEY") or None
URLS = [u.strip().rstrip("/") for u in (os.environ.get("POOL_SERVERS") or "").split(",") if u.strip()]
POOL = Pool(URLS or ["http://localhost:8001"], switch_at=_env_int("POOL_SWITCH_AT", 23),
            warm_at=_env_int("POOL_WARM_AT", 10), rest_seconds=_env_int("POOL_REST_SECONDS", 60))

KEEP_WARM = max(0, _env_int("POOL_KEEP_WARM", 1))
KEEP_WARM_SECONDS = min(KEEP_WARM_MAX, max(KEEP_WARM_MIN, _env_int("POOL_KEEP_WARM_SECONDS", 240)))

_status_lock = threading.Lock()
_status = {"last_ok_at": None, "last_error_at": None, "last_error": None}

app = bottle.Bottle()


def _iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def _json(data, status=200):
    bottle.response.status = status
    bottle.response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def _key_ok():
    given = bottle.request.get_header("X-Route-Key") or ""
    return not KEY or hmac.compare_digest(given.encode(), KEY.encode())


def _headers():
    h = {"accept": "application/json"}
    if KEY:
        h["X-Route-Key"] = KEY
    return h


def _warm(i):
    def run():
        req = urllib.request.Request(POOL.urls[i] + "/warm", data=b"", method="POST", headers=_headers())
        try:
            urllib.request.urlopen(req, timeout=WARM_TIMEOUT).read()
        except Exception as e:
            print(f"pool: warming container {i + 1} failed: {e}", flush=True)
    threading.Thread(target=run, daemon=True, name=f"pool-warm-{i + 1}").start()


def _keep_warm_loop():
    """Ask the first POOL_KEEP_WARM containers to open (or keep) Chrome, now
    and every KEEP_WARM_SECONDS: /warm opens it when closed and resets its
    idle clock when open, without a Waze call."""
    while True:
        for i in POOL.keep_warm_targets(KEEP_WARM):
            _warm(i)
        time.sleep(KEEP_WARM_SECONDS)


def _forward(path_qs):
    """(status, body) from the first container that can serve the query."""
    tried, last = set(), "no container available"
    for _ in range(len(POOL.urls)):
        i, warm = POOL.take(skip=tried)
        if i is None:
            break
        tried.add(i)
        if warm is not None:
            _warm(warm)
        req = urllib.request.Request(POOL.urls[i] + path_qs, headers=_headers())
        try:
            with urllib.request.urlopen(req, timeout=FORWARD_TIMEOUT) as res:
                POOL.succeeded(i)
                return res.status, res.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code in (400, 404):            # Waze's own answer: pass it back
                POOL.succeeded(i)
                return e.code, body
            last = f"container {i + 1}: HTTP {e.code} {body[:120]!r}"
        except Exception as e:
            last = f"container {i + 1}: {type(e).__name__}: {e}"
        POOL.failed(i, last)
        print(f"pool: {last}", flush=True)
    return None, last


@app.get("/")
@app.get("/health")
def health():
    out = {"status": "ok", "pool": len(POOL.urls)}
    if _key_ok():
        with _status_lock:
            st = dict(_status)
        out["waze"] = {"last_ok_at": _iso(st["last_ok_at"]), "last_error_at": _iso(st["last_error_at"]),
                       "last_error": st["last_error"]}
        out["containers"] = POOL.status()
    return _json(out)


@app.get("/<path:path>")
def proxy(path):
    if not _key_ok():
        return _json({"error": "missing or wrong X-Route-Key"}, 401)
    qs = bottle.request.query_string
    status, body = _forward("/" + path + ("?" + qs if qs else ""))
    with _status_lock:
        if status is None:
            _status["last_error_at"], _status["last_error"] = time.time(), body[:200]
        else:
            _status["last_ok_at"] = time.time()
    if status is None:
        return _json({"error": f"every container is busy or failing ({body})"}, 503)
    bottle.response.status = status
    bottle.response.content_type = "application/json"
    return body


def main():
    if not URLS:
        raise SystemExit("Set POOL_SERVERS to the containers, in order (comma-separated URLs).")
    port = _env_int("PORT", 8000)
    print(f"GET.route pool: {len(URLS)} containers, next after {POOL.switch_at}/min, "
          f"warm at {POOL.warm_at}, keeping {KEEP_WARM} warm every {KEEP_WARM_SECONDS} s; "
          f"listening on :{port}", flush=True)
    if KEEP_WARM:
        threading.Thread(target=_keep_warm_loop, daemon=True, name="pool-keep-warm").start()
    server = wsgi.Server(("0.0.0.0", port), app, server_name="get-route-pool", numthreads=32)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
