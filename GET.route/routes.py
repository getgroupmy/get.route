"""The 6 Waze endpoints. Every path is served with and without the `/waze`
prefix, so code generated against the hosted API on RapidAPI (paths like
/jams/search) runs unchanged against this server.

Params are validated by the same schemas the hosted API uses
(waze/schemas.py): a bad or unknown param is a 400 that names the field."""
import hmac
import json

from bottle import hook, request, response, route

import config

from schema_fields import load_query
from waze import api, schemas
from waze.fetch import WazeBadRequest, WazeNotFound


OPEN_PATHS = {"/", "/health"}


@hook("before_request")
def require_key():
    """With ROUTE_API_KEY set, every endpoint but the health check needs the
    same value in the X-Route-Key header (GET.ride's ai-route-proxy sends
    it). Without it the API is open, as before: fine on your own computer,
    never behind a public tunnel."""
    expected = config.route_api_key()
    if not expected or request.path in OPEN_PATHS:
        return
    given = request.get_header("X-Route-Key") or ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        from bottle import HTTPResponse
        raise HTTPResponse(json.dumps({"error": "missing or wrong X-Route-Key"}), status=401,
                           headers={"Content-Type": "application/json"})


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Zürich" would arrive as "ZÃ¼rich")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def call(label, schema, fn):
    """Validate the query with `schema`, run `fn(**params)` and map errors:
    bad params -> 400, unknown place -> 404, Waze failures -> 500."""
    data, error = load_query(schema, query_dict())
    if error:
        return json_response(error, 400)
    try:
        return json_response(fn(**data))
    except ValueError as e:                # bad id / params
        return json_response({"error": str(e)}, 400)
    except WazeBadRequest as e:            # Waze rejected the request (e.g. no route)
        return json_response({"error": f"waze rejected the request: {e}"}, 400)
    except WazeNotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / no token
        return json_response({"error": f"waze {label} failed: {e}"}, 500)


ENDPOINTS = [
    ("/jams/search", schemas.JamsSearchSchema, api.jams_search),
    ("/alerts/search", schemas.AlertsSearchSchema, api.alerts_search),
    ("/routes/search", schemas.RoutesSearchSchema, api.routes_search),
    ("/places/search", schemas.PlacesSearchSchema, api.places_search),
    ("/places/details", schemas.PlaceDetailsSchema, api.place_details),
    ("/geocode/reverse", schemas.ReverseGeocodeSchema, api.geocode_reverse),
]


def mount(path, schema, fn):
    """Serve one endpoint at /path and /waze/path."""
    label = path.strip("/")

    def handler():
        return call(label, schema, fn)
    handler.__name__ = "waze_" + label.replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/waze" + path, method="GET")(handler)


for _path, _schema, _fn in ENDPOINTS:
    mount(_path, _schema, _fn)


def _iso(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


@route("/", method="GET")
@route("/health", method="GET")
def health():
    """Always open. With the right X-Route-Key (or no key configured) it also
    says how the latest Waze calls went, which GET.ride's health check uses
    to tell the admins when Waze starts refusing this server. It spends no
    Waze call."""
    out = {"status": "ok", "endpoints": [p for p, _, _ in ENDPOINTS]}
    expected = config.route_api_key()
    given = request.get_header("X-Route-Key") or ""
    if not expected or hmac.compare_digest(given.encode(), expected.encode()):
        from waze.fetch import recent_status
        st = recent_status()
        out["waze"] = {"last_ok_at": _iso(st["last_ok_at"]), "last_error_at": _iso(st["last_error_at"]),
                       "last_error": st["last_error"]}
    return json_response(out)
