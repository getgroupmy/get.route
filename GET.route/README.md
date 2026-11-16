# GET.route

GET.route gives GET.ride live Waze traffic for fares: the real road distance,
the drive time in current traffic, and the tolls on the way. It reads the same
JSON API the Waze live map (waze.com/live-map) uses, through a real Google
Chrome that earns the reCAPTCHA token Waze asks for.

In production it runs on the office NAS as a pool of 16 containers behind one
dispatcher, reached through a Cloudflare Tunnel at `https://route.getride.my`.
GET.ride's `ai-route-proxy` asks it as the **Waze** step of the fare data
order (Admin › Settings › Fare AI provider), usually first: **Waze, then
Google Maps, then Apple Maps, then AI, then OSRM**. The Waze / Google Maps /
Apple Maps balance can send a share of fares to Google Maps or Apple Maps
first; Waze takes the rest.

```
 rider app ──► ai-route-proxy ──https──► route.getride.my ──► Cloudflare Tunnel ──► get-route-pool ──► get-route-01 … 16
 (GET.ride)    (Supabase)      X-Route-Key                                          (pool_server.py)    (run.py + Chrome)
```

Based on [omkarcloud/waze-scraper](https://github.com/omkarcloud/waze-scraper)
(MIT, see `LICENSE`), changed for GET.ride as described below.

## What GET.ride uses

- **`/routes/search`** for every fare: GET.ride asks for one route
  (`max_routes=1`) per leg and adds up the legs of a trip with stops. It
  reads the distance, the drive time and the toll price. Waze gets
  **2 seconds** per trip by default (every leg included), then the fare
  goes to the next step. Admins set it, and every other step's time, in
  **Admin › Fare AI provider › Time limits**, along with how long the rider
  app waits in all (7 s).
- **`/health`** once a minute (`waze-server-health`). With the key it also
  says when the last Waze call worked or failed, so GET.ride can tell
  admins when Waze starts refusing the server, without spending a Waze
  call.

The other endpoints work the same way and are there for later use.

## Endpoints

Every path also answers under `/waze` (e.g. `/waze/routes/search`). With
`ROUTE_API_KEY` set, every call except `/health` needs the header
`X-Route-Key: <key>`.

| Path | Returns | Main parameters |
|---|---|---|
| `GET /routes/search` | Up to 3 driving routes: live ETA, distance, tolls, jams and alerts on the way | `from`, `to` (lat,lng, a Waze venue id, a Google place id, or a waze.com link), `depart_at` or `arrive_at` (ISO 8601), `max_routes` (1-3) |
| `GET /jams/search` | Traffic jams around a point, worst first | `location` (lat,lng or a box south,west,north,east), `radius_km` (default 5, max 50), `min_level` (0-5), `limit` |
| `GET /alerts/search` | Road closures and incidents, newest first | `location`, `radius_km`, `types`, `limit` |
| `GET /places/search` | Places and addresses with coordinates and a place id | `query`, `near`, `language`, `limit` (max 20) |
| `GET /places/details` | Address, phone, opening hours, services and photos | `place` (Waze venue id, Google place id or link), `language` |
| `GET /geocode/reverse` | Street, city and time zone for a point | `location` |
| `GET /health` | `{"status": "ok"}`; with the key also `waze` (last call ok / failed) and `chrome` (open / closed) | none |
| `POST /warm` | Opens Chrome ahead of traffic, without spending a Waze call | none |

A bad or unknown parameter is a `400` that names it; no route between two
points (or a trip over 3,000 miles) is a `400` with Waze's reason; an
unknown place is a `404`; Waze failing after its retries is a `500`.

Example, KLCC to KL Sentral:

```bash
curl -H "X-Route-Key: $ROUTE_API_KEY" \
  "https://route.getride.my/routes/search?from=3.158,101.712&to=3.134,101.686&max_routes=1"
```

## How it works

1. **Tokens.** Every Waze live-map call carries a reCAPTCHA Enterprise token.
   Waze scores it, and refuses tokens from headless Chrome or captcha
   services. So the first call opens one headed Google Chrome
   (`browser_client.py`, `patchright_driver.py`; on a server without a
   screen it starts a virtual one), visits google.com, parks on the live
   map and mints tokens there. Chrome closes after 10 idle minutes.
2. **Budget.** A token serves about 5 calls, and about 5 are minted a
   minute, so one container makes about **25 Waze calls a minute**. Tokens
   are not tied to an IP, but their score is better from an office or home
   connection than from a cloud server.
3. **Calls.** `waze/fetch.py` calls the live-map API with `curl_cffi`
   (Chrome's TLS fingerprint) and the token; a refused token is swapped and
   the call retried. `waze/parsers.py` turns the answers into the JSON
   above.
4. **Cache.** Answers are kept in memory: routes 5 minutes, jams and
   alerts 2 minutes, places and addresses 12-24 hours. A rider adjusting the
   same trip is answered from the cache in about 0.15 s.
5. **Regions.** Waze has three clusters (`na`, `row`, `il`); Malaysia is
   `row`, chosen from the coordinates.

## The pool (16 containers)

`pool_server.py` is the dispatcher in front of the containers; its rules are
in `pool.py`:

- Every query goes to container 01 until it has served **23 queries in the
  last minute**; the next goes to 02, and so on. As the minute rolls on,
  traffic falls back to 01.
- When a container serves its **10th query of the minute**, the next one is
  told to open Chrome (`POST /warm`), so it is ready before traffic reaches
  it.
- Container 01 is kept warm between fares: every 4 minutes the dispatcher
  asks it to open (or keep) Chrome, so on a quiet day a fare doesn't meet a
  container still starting Chrome (20-40 s, longer than GET.ride waits). If
  01 is resting, 02 is kept warm instead. No Waze call is spent.
- A container that fails (no answer, 5xx, refused key) rests 60 seconds and
  the query moves on. Waze's own 400 / 404 answers are passed back.
- Its `/health` (with the key) lists each container's load, rest and last
  error.

Capacity is about 16 × 23 ≈ 368 Waze calls a minute. The thresholds are
`POOL_SWITCH_AT`, `POOL_WARM_AT`, `POOL_REST_SECONDS` and `POOL_KEEP_WARM`.

**Deploying on the office NAS:** see [`deploy/nas/README.md`](deploy/nas/README.md)
(compose file, tunnel, `.env`, memory, the subdomain-worker pass-through and
the Admin steps).

## Running it on your own computer

You need Python 3 and Google Chrome.

```bash
python -m pip install -r requirements.txt
```

```bash
python run.py
```

Then, in another terminal:

```bash
curl "http://localhost:8000/routes/search?from=3.158,101.712&to=3.134,101.686&max_routes=1"
```

The first call opens a Chrome window and takes 20-40 seconds; leave the
window open. `main.py` calls the same functions from Python without a
server. `docker compose up --build` runs one container (Chrome and a virtual
screen are in the image).

## Settings

| Variable | Default | What it does |
|---|---|---|
| `PORT` | `8000` | The port the API (or the dispatcher) listens on. |
| `ROUTE_API_KEY` | none | When set, every call but `/health` needs it in `X-Route-Key`. Always set it when the API is reachable from outside the machine. |
| `WAZE_PROXY` | none | A proxy for the calls to Waze (`http://user:pass@host:port`). Not needed: Waze limits tokens, not IPs. |
| `POOL_SERVERS` | none | Dispatcher only: the containers, in order, comma-separated. |
| `POOL_SWITCH_AT` / `POOL_WARM_AT` / `POOL_REST_SECONDS` | `23` / `10` / `60` | Dispatcher only: see "The pool". |
| `POOL_KEEP_WARM` / `POOL_KEEP_WARM_SECONDS` | `1` / `240` | Dispatcher only: how many of the first containers keep Chrome open between fares (0 = off), and how often they are asked (30-540 s, under the containers' 600 idle seconds). |

Token limits, retries and cache times are constants in `config.py` and
`waze/cache_config.py`.

## Tests

```bash
python -m pytest -q waze test_pool.py
```

The parser tests run against saved Waze answers in `waze/fixtures/`; the pool
tests check the dispatcher's rules. Neither needs a network or Chrome.

## Things to know

- **Waze's terms.** This reads Waze's private live-map API through an
  automated browser, which Waze's terms very likely forbid. GET.ride keeps
  other steps after Waze in the fare order (Apple Maps' official API, the
  AI, OSRM), so fares keep working if Waze blocks it.
- **Speed matters more than load.** On a quiet day the risk is a container
  still starting Chrome, not too many calls; that is what keeping
  container 01 warm is for (see "The pool").
- **It can break when Waze changes.** The reCAPTCHA site key, the API paths
  and the answer shapes are taken from the live map's code as of November
  2026.
- **Tokens are the limit,** not bandwidth or the IP: each container makes
  about 25 Waze calls a minute.

## Files

| File | Role |
|---|---|
| `run.py`, `routes.py` | The HTTP API (bottle + cheroot), the key check, `/health`, `/warm` |
| `pool.py`, `pool_server.py` | The dispatcher's rules and server |
| `waze/api.py` | The endpoints: areas, regions, cache, tiling of large boxes |
| `waze/fetch.py` | Calls to Waze with tokens, retries, last-call status |
| `waze/token.py`, `identity_pool.py` | The token pool |
| `browser_client.py`, `patchright_driver.py` | Chrome: open, warm, mint |
| `waze/parsers.py`, `waze/schemas.py`, `waze/refs.py` | Answers, parameters, ids and links |
| `config.py`, `waze/cache_config.py` | Settings and cache times |
| `deploy/nas/` | The office NAS deployment |
