# GET.route console (waze.getcdn.link, waze2.getcdn.link)

One standalone service in front of the office Waze servers, for GET's own
apps. Each app (GET.ride, GET.teksi, ...) calls it with its own key; the
console asks the Waze servers in the order you set and moves on when one
doesn't answer. The console at `/admin` is where people sign in, as on
GET.ekyc.

It runs twice, so Waze keeps working when either machine is down:

```
                ┌─► waze.getcdn.link  ─► console on the Mac mini (deploy/mac) ─┬─► Mac pool   first
 GET.ride ──────┤   (Waze server 1)                                            └─► NAS pool   second
 (one key per   │
  app on each)  └─► waze2.getcdn.link ─► console on the NAS (this folder)     ─┬─► NAS pool   first
                    (Waze server 2)                                            └─► Mac pool   second
```

GET.ride lists both as Waze servers and moves to `waze2` when `waze` doesn't
answer. The two consoles share nothing: each has its own apps and keys,
servers, log, users and audit trail. This README sets up the NAS one; the
Mac one is in [`deploy/mac/README.md`](deploy/mac/README.md).

**For GET's own apps only.** It serves Waze's live-map data, read through an
automated Chrome, which Waze's terms very likely forbid. It is not a product
to offer to other companies.

## What it does

- **The same API as GET.route**, so an app that already talks to a Waze
  server only needs the new address and key: `GET /routes/search`,
  `/jams/search`, `/alerts/search`, `/places/search`, `/places/details`,
  `/geocode/reverse` (each also under `/waze/...`), `POST /warm`, and
  `GET /health`. The parameters and answers are GET.route's
  (`GET.route/README.md`).
- **One key per app**, sent as `X-Route-Key` (or `X-API-Key`), with its own
  limit of calls a minute. Keys are shown once, stored only as a hash, and
  can be revoked or replaced at any time.
- **Servers in order, with failover.** A call goes to the first server that
  is on and not resting, within that server's time (3 s by default) and the
  call's total time (8 s). A server that doesn't answer, answers 5xx or 429,
  or refuses its key rests (60 s by default) and the call moves to the next
  one. Waze's own answers (no route, unknown place) are passed back as they
  are. If every server is resting, they are all tried anyway.
- **Health every minute.** Each server's `/health` with its key: online, or
  offline with the reason (unreachable, key refused, Waze refusing it).
- **`/health`** is open; with an app's key it adds when the service last
  answered and last failed (`waze`, as GET.route's own `/health` does, which
  GET.ride's minute-by-minute check reads) and each server's state.
- **Request log** of every call: which app, which endpoint, which server
  answered, the result and the time. No places, coordinates or keys are
  kept. Kept 30 days by default.

## The console (`/admin`)

| Tab | What it is for |
|---|---|
| Overview | Calls, share answered, median and 9-in-10 times, calls by hour, by app and by server, each server's health |
| Request log | The newest 200 calls, or only the failures |
| Apps | Create an app's key, change its limit, replace or revoke its key |
| Servers | Add the Mac mini and the NAS pool with their keys, set the order (**Ask earlier**), time and rest, turn them on and off, end a rest, and **Test** one (its health and one route) |
| Try it | One route through the service, exactly as an app's call goes |
| Settings | The most time for one call, a new app's limit, how long the log is kept |
| Admins | Console users and their roles (owner, admin, developer, viewer) |
| Audit | Every change, by whom; **Check it hasn't been changed** verifies the hash chain |

Sign in with a username and password (scrypt-hashed, 5 wrong tries lock the
name for 15 minutes), or with the admin token. The first time, sign in with
the token and create your own user under **Admins**. The servers' keys are
encrypted with `WZ_SECRET_KEY` and never shown again after you save them.

## Set it up on the NAS

It runs next to the NAS pool, in GET.route's Docker network, and uses
GET.route's Cloudflare Tunnel; it needs no browser and little memory (capped
at 256 MB).

1. Make its folder and data folder (over SSH), owned by the container's
   user (uid 10002):

   ```bash
   sudo mkdir -p /volume1/docker/get-route-console/data && sudo chown 10002 /volume1/docker/get-route-console/data && sudo chmod 700 /volume1/docker/get-route-console/data
   ```

2. Put the compose file in that folder as `compose.yaml`, building straight
   from GitHub as the NAS pool does (the office NAS does this; no copy of the
   code is needed): `docker-compose.yml` from this folder, with
   `build: .` changed to
   `build: https://github.com/getgroupmy/get.route.git#main:console` and
   `${WZ_DATA_PATH}` replaced by `/volume1/docker/get-route-console/data`.
3. Make `.env` there. This makes the admin token and the secret key on the
   NAS (never typed or shown) and finds GET.route's Docker network:

   ```bash
   cd /volume1/docker/get-route-console && NET=$(sudo docker inspect get-route-pool --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' | awk '{print $1}') && printf 'WZ_ADMIN_TOKEN=%s\nWZ_SECRET_KEY=%s\nWZ_PUBLIC_URL=https://waze2.getcdn.link\nGET_ROUTE_NETWORK=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -base64 32)" "$NET" | sudo tee .env > /dev/null && sudo chmod 600 .env && echo "network: $NET"
   ```

   Start it:

   ```bash
   cd /volume1/docker/get-route-console && sudo docker compose up -d --build
   ```

4. In Cloudflare Zero Trust › Networks › Tunnels, open **GET.route's tunnel**
   › Public Hostname › **Add**: `waze2.getcdn.link` → **HTTP**
   `get-route-console:8080`. `getcdn.link` is not behind GET.ride's subdomain
   worker, so nothing else is needed.
5. Protect the console: a Cloudflare Access policy (or a WAF rule) on
   `waze2.getcdn.link/admin*`, as for GET.ekyc, so only your team reaches the
   sign-in page. The API itself needs an app key for every call.
6. Open `https://waze2.getcdn.link/admin`, sign in with the admin token, and
   create your user under **Admins**.
7. **Servers**: add, in this order:
   - **NAS pool**: `http://get-route-pool:8000` with the NAS's
     `ROUTE_API_KEY`.
   - **Mac mini**: `http://192.168.0.101:8100` with the Mac's `ROUTE_API_KEY`
     (`GET.route/deploy/mac`, with `POOL_HOST=0.0.0.0`; the Mac has that
     fixed address on the office network).

   Tap **Test** on each.
8. **Apps**: create one for GET.ride and copy its key.
9. In GET.ride, **Admin › Settings › Fare AI provider › Waze servers**:
   `https://waze2.getcdn.link` with that key, below `https://waze.getcdn.link`
   (the Mac's console). **Test**, then **Save changes**.

## Check and update

- From anywhere: `https://waze2.getcdn.link/health` answers
  `{"status": "ok", "servers": 2, "servers_online": 2}`.
- On the NAS: `sudo docker logs get-route-console 2>&1 | tail -20`.
- Update to the latest `main` (`.env` and `data/` are kept):

  ```bash
  cd /volume1/docker/get-route-console && sudo docker compose build --no-cache && sudo docker compose up -d
  ```

- Back up `data/` together with `.env` with the NAS's other backups;
  without `WZ_SECRET_KEY` the servers' keys in the database can't be read.

## Settings (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `WZ_ADMIN_TOKEN` | required | The owner's way in (24+ characters). Changing it signs everyone out. |
| `WZ_SECRET_KEY` | required | 32 random bytes, base64: encrypts the servers' keys and signs sign-ins. |
| `WZ_PUBLIC_URL` | none | The address apps use, shown in the console (`https://waze2.getcdn.link` on the NAS). |
| `WZ_TOTAL_TIMEOUT_MS` | `8000` | Starting value; change it in **Settings**. |
| `WZ_DEFAULT_RATE_PER_MINUTE` | `300` | Starting value; change it in **Settings**. |
| `WZ_LOG_RETENTION_DAYS` | `30` | Starting value; change it in **Settings**. |
| `WZ_HEALTH_EVERY_SECONDS` | `60` | How often each server's `/health` is checked. |

## Run it on your computer

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

```bash
WZ_ADMIN_TOKEN=$(openssl rand -hex 32) WZ_SECRET_KEY=$(openssl rand -base64 32) WZ_DATA_DIR=./data .venv/bin/uvicorn app.main:app --port 8080
```

Then `http://localhost:8080/admin`, signing in with the token printed in that
shell's history.

## Tests

```bash
.venv/bin/python -m pytest -q
```

They run against stand-in Waze servers: forwarding with each server's own
key, failover and resting, Waze's own 400 passed back, every server failing,
the per-app limit, the server order, keys encrypted at rest, the request log
keeping no places, sign-in and roles, the audit trail's tamper check, Try it,
the server test and the health check.

## Files

| File | What it does |
|---|---|
| `app/main.py` | The app: routes, the console page, start-up |
| `app/routers/api.py` | The API your apps call, and `/health` |
| `app/proxy.py` | Servers in order, failover, rests, the per-app limit |
| `app/health.py` | The minute-by-minute health check, log clean-up |
| `app/routers/admin.py`, `app/routers/session.py` | The console's API and sign-in |
| `app/auth.py`, `app/permissions.py` | Keys, passwords, sessions, roles |
| `app/db.py`, `app/crypto.py`, `app/config.py` | Database, encryption, settings |
| `app/static/admin.html` | The console |
| `deploy/mac/` | The same console on the Mac mini: start script, launchd file, set-up |
