# GET.route on the office NAS

GET.route answers GET.ride's Fare AI with Waze's live route: real distance,
traffic-aware time and tolls. On the NAS it runs as **a pool of 16 Waze
containers behind one dispatcher**, for all of Malaysia. GET.ride sees a
single Waze server.

```
 ai-route-proxy ──https──► route.getride.my ─ Tunnel ─► get-route-pool ──► get-route-01  (Chrome + API)
 (Supabase)      X-Route-Key              (cloudflared)  (dispatcher)  ├─► get-route-02
                                                                       ├─► …
                                                                       └─► get-route-16
```

## How the pool shares the work

- **One container at a time.** Every query goes to `get-route-01` until it
  has served **23 queries in the last minute**; the 24th goes to `02`, and
  so on down the line. As the minute rolls on, traffic falls back to `01`.
  (Each container's Chrome mints a token about every 12 s and a token serves
  ~5 calls, so ~25 a minute; 23 leaves a margin.)
- **The next one is warmed ahead of time.** When a container serves its
  **10th query of the minute**, the dispatcher tells the next one to open
  Chrome (20–40 s), so it is ready before the spill-over reaches it. Warming
  spends no Waze call.
- **The first container stays warm.** Every 4 minutes the dispatcher asks
  `get-route-01` to open (or keep) Chrome, so on a quiet day fares don't
  meet a container still starting Chrome, which takes longer than GET.ride
  waits. If 01 is resting after a failure, 02 is kept warm instead.
  `POOL_KEEP_WARM` (how many, `0` = off) and `POOL_KEEP_WARM_SECONDS` in
  `.env`.
- **Idle containers cost little.** Any other container with no work closes
  Chrome after 10 minutes, so on a normal day only one or two hold real
  memory (about 1 GB with 01 always open).
- **Failures are skipped.** A container that does not answer, answers 5xx,
  or refuses the key rests for 60 s and the query is retried on the next
  one. Waze's own "no route" (400) and "not found" (404) are passed back.
- **Capacity:** 16 × 23 ≈ 368 Waze calls a minute in all. A trip with stops
  costs one call per leg.

The numbers are in `.env` (`POOL_SWITCH_AT`, `POOL_WARM_AT`,
`POOL_REST_SECONDS`, `POOL_KEEP_WARM`, `POOL_KEEP_WARM_SECONDS`); the rules are in `pool.py`, tested in `test_pool.py`.

**Bursts.** Steady traffic never waits for Chrome. If queries 10 to 24 of
a minute all arrive within the 20–40 s the next container needs to start,
the first spill-over queries wait for it (up to about a minute). Lower
`POOL_WARM_AT` if that happens often.

**Monitoring.** GET.ride checks the dispatcher every minute. Fare AI admins
get a push when the pool has failed queries for 5 minutes (every container
busy or failing, or the NAS / tunnel down) and when it serves again. A
single broken container is skipped without an alert; see it in
`https://route.getride.my/health` with the key (`containers`: each one's
load, rest and last error):

```bash
curl -s -H "X-Route-Key: $ROUTE_API_KEY" https://route.getride.my/health
```

## Security

- **No port is opened** on the NAS or the router: `cloudflared` makes an
  outgoing connection and Cloudflare sends `route.getride.my` down it. Only
  the dispatcher is in the tunnel; the containers have no hostname.
- Every call except `/health` needs the secret header `X-Route-Key`. The
  dispatcher and all containers share the one key.
- Chrome runs inside the containers on the office connection. Waze scores
  the tokens it makes; an office or home connection scores far better than
  a cloud server, which is why this runs here.

## What the NAS needs

- Synology DSM 7.2+ with **Container Manager**, x86-64 (the Chrome image
  is amd64 only).
- 3 GB of disk for the image, which every container shares.
- A Cloudflare account with the `getride.my` zone.

### Memory and CPU

The DS224+ has 18 GB (its maximum) and a 4-core Celeron J4125. Each
container is capped at 1 GB (`MEM_PER_SERVER`), but only containers with
Chrome open use much of it, and the pool keeps that to as few as the
traffic needs: one for up to ~23 calls a minute, two for ~46, and so on.
These are estimates; nothing has been measured on the NAS yet. Watch
Resource Monitor through a busy day: RAM under about 85% and CPU not
pinned at 100% means you are fine.

## Set it up

1. Make a folder for the project on the NAS, e.g.
   `/volume1/docker/get-route`. Either copy this repository's `GET.route`
   folder there, or (as the office NAS does) let Docker build straight from
   GitHub: put only the compose file there, saved as `compose.yaml`, with
   every `build: ../..` line changed to
   `build: https://github.com/getgroupmy/get.route.git#main:GET.route`.
   Then the NAS needs no copy of the code, and a rebuild fetches the latest
   `main`.
2. In Cloudflare Zero Trust › Networks › Tunnels, create a tunnel
   (Docker). Copy the token. Add **one** public hostname:
   `route.getride.my` → `http://get-route-pool:8000`.

   GET.ride's subdomain worker (`cloudflare/subdomain-proxy` in
   getgroupmy/get-ride) answers every `*.getride.my` name with the web app,
   tunnel hostnames included, unless the name is in its pass-through list.
   `route` is in `PASS_THROUGH` in its `wrangler.toml`; if the repository
   variable `SUBDOMAIN_PROXY_PASS_THROUGH` is set, it replaces that list,
   so `route` must be in the variable too (e.g. `stats,route`).
3. Next to the compose file, copy `.env.example` to `.env`; set
   `TUNNEL_TOKEN` and `ROUTE_API_KEY` (`openssl rand -hex 32`).
4. Start it: Container Manager › Project › Create, with the folder from
   step 1, or over SSH from that folder (`deploy/nas` in a copy):

   ```bash
   cd /volume1/docker/get-route/deploy/nas && sudo docker compose up -d --build
   ```

5. Check it from anywhere: `https://route.getride.my/health` answers
   `{"status": "ok", "pool": 16}`. If it shows the GET.ride web page
   instead, the subdomain worker is still catching `route` (step 2).
6. In GET.ride, **Admin › Settings › Fare AI provider**: pick a fare data
   order with Waze in it (e.g. **Waze, then Google Maps, then Apple Maps,
   then AI, then OSRM**). On the Waze server card for
   `https://route.getride.my` (add one if there is none; leave its area on
   **All regions**), paste the `ROUTE_API_KEY`, switch it on, tap **Test**,
   then **Save changes**. Fares the pool can't answer within Waze's time
   (2 s by default, **Time limits** on the same page) go to the next step.

The first query opens Chrome in `get-route-01` (about 20–40 s); after that
answers take about 1–3 s.

## Update it

With the build from GitHub (step 1), rebuild the dispatcher, or every
container when the change is in the containers' code, from the project
folder:

```bash
cd /volume1/docker/get-route && sudo docker compose up -d --build get-route-pool
```

```bash
cd /volume1/docker/get-route && sudo docker compose up -d --build
```

With a copy, copy the new files in first (keep your `.env`). Then check the
dispatcher picked it up:

```bash
sudo docker logs get-route-pool 2>&1 | tail -3
```

It starts with a line like `GET.route pool: 16 containers, next after 23/min,
warm at 10, keeping 1 warm every 240 s`. To see Chrome in container 01, ask
its own `/health` with the key (it is never printed):

```bash
sudo docker exec get-route-01 python -c "import urllib.request,os;r=urllib.request.Request('http://localhost:8000/health',headers={'X-Route-Key':os.environ['ROUTE_API_KEY']});print(urllib.request.urlopen(r).read().decode())"
```

`"chrome": "open"` is what keep-warm holds it at.
