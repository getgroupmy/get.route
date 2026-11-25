# The GET.route console on the Mac mini (waze.getcdn.link)

Two consoles, so Waze keeps working when either machine is down:

```
                    ┌─► waze.getcdn.link  ─ Mac's tunnel ─► console on the Mac ─┬─► Mac pool   http://127.0.0.1:8100      first
 GET.ride ──────────┤   (Waze server 1)                                         └─► NAS pool   http://192.168.0.13:8100   second
 (Waze servers)     │
                    └─► waze2.getcdn.link ─ NAS's tunnel ─► console on the NAS ─┬─► NAS pool   http://get-route-pool:8000 first
                        (Waze server 2)                                         └─► Mac pool   http://192.168.0.101:8100  second
```

- **Every day:** GET.ride asks `waze.getcdn.link`, the console on the Mac,
  which asks the Mac's own pool first and the NAS pool over the office
  network if the Mac's pool fails.
- **Mac down** (off, asleep, its tunnel down): `waze.getcdn.link` doesn't
  answer, so GET.ride asks its second Waze server, `waze2.getcdn.link`, the
  console on the NAS.
- **NAS down:** nothing changes for fares; the Mac console only loses its
  second server.

The two consoles don't share anything: each has its own apps and keys,
servers, request log, users and audit trail. A change in one (a new app, a
new server key) is made in the other too.

It runs straight on macOS, like GET.route's pool on this Mac
(`GET.route/deploy/mac`), started by launchd at login. It listens on this Mac
only (`127.0.0.1:8200`); its own Cloudflare Tunnel brings
`waze.getcdn.link` to it.

## 1. Install it (on the Mac)

The repository is already in `~/get.route` from the pool's set-up. Update it:

```bash
cd ~/get.route && git pull
```

It needs Python 3.10 or later:

```bash
python3 --version
```

If that says 3.9 or older, install Python from python.org (macOS installer)
and open a new Terminal window. Then:

```bash
cd ~/get.route/console && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## 2. Its settings

This makes the admin token and the secret key on the Mac, without showing
them:

```bash
cd ~/get.route/console/deploy/mac && printf 'WZ_ADMIN_TOKEN=%s\nWZ_SECRET_KEY=%s\nWZ_PUBLIC_URL=https://waze.getcdn.link\nWZ_PORT=8200\n' "$(openssl rand -hex 32)" "$(openssl rand -base64 32)" > .env && chmod 600 .env && echo made
```

Port 8200 must be free (nothing printed):

```bash
lsof -nP -iTCP:8200 -sTCP:LISTEN
```

If something uses it, change `WZ_PORT` in `.env` and use that port below.

## 3. Start it at login

```bash
mkdir -p ~/get.route/console/deploy/mac/logs && sed "s|/Users/YOU/get.route|$HOME/get.route|g" ~/get.route/console/deploy/mac/com.getride.getroute-console.plist > ~/Library/LaunchAgents/com.getride.getroute-console.plist && launchctl load -w ~/Library/LaunchAgents/com.getride.getroute-console.plist
```

```bash
sleep 5; curl -s http://127.0.0.1:8200/health; echo
```

It answers `{"status":"degraded","servers":0,"servers_online":0}` until it
has servers (step 6).

## 4. The NAS pool on the office network

The Mac console asks the NAS pool directly, so the pool answers on the
office network too (port 8100, with its key, like the Mac's). On the NAS,
next to GET.route's `compose.yaml`:

```bash
cd /volume1/docker/get-route && printf 'services:\n  get-route-pool:\n    ports:\n      - "8100:8000"\n' | sudo tee compose.override.yaml > /dev/null && sudo docker compose up -d get-route-pool
```

Check from the Mac:

```bash
curl -s -m 5 http://192.168.0.13:8100/health; echo
```

`{"status": "ok", "pool": 16}`.

## 5. The Mac's Cloudflare Tunnel

1. Cloudflare Zero Trust › **Networks › Tunnels › Create a tunnel ›
   Cloudflared**, named `GET.route Mac`. Choose **macOS** and copy the token
   from the install command it shows.
2. On the Mac, install `cloudflared` and run it as a service with that token
   (Homebrew; or the `.pkg` from Cloudflare's downloads page):

   ```bash
   brew install cloudflared
   ```

   ```bash
   sudo cloudflared service install PASTE_THE_TOKEN
   ```

   The tunnel shows **Healthy** in Zero Trust.

Its public hostname is added in step 7, when `waze.getcdn.link` moves over.

## 6. Set the console up

Open it on the Mac at `http://127.0.0.1:8200/admin`, or from another
computer through SSH (`ssh -L 8200:127.0.0.1:8200 mini`, then
`http://localhost:8200/admin` there). Sign in with the admin token:

```bash
grep ^WZ_ADMIN_TOKEN ~/get.route/console/deploy/mac/.env | cut -d= -f2 | tr -d '\n' | pbcopy && echo "token copied"
```

1. **Admins:** your own user, role owner.
2. **Servers**, in this order:
   - **Mac pool**: `http://127.0.0.1:8100`, the Mac's `ROUTE_API_KEY`
     (`grep ^ROUTE_API_KEY ~/get.route/GET.route/deploy/mac/.env | cut -d= -f2 | tr -d '\n' | pbcopy`),
     time 2000 ms.
   - **NAS pool**: `http://192.168.0.13:8100`, the NAS's `ROUTE_API_KEY`
     (on the NAS: `sudo docker exec get-route-pool printenv ROUTE_API_KEY`),
     time 3000 ms.

   **Test** each.
3. **Apps:** `GET.ride fares`, **Create key**, and keep it for step 7.

## 7. Move the names

So that `waze.getcdn.link` is the Mac's console and `waze2.getcdn.link` the
NAS's. GET.ride keeps answering throughout: while a name moves, its other
Waze server or the later fare steps answer.

1. **waze2 on the NAS.** Zero Trust › Tunnels › **GET.route's tunnel** (the
   NAS's) › Public hostnames › **Add**: `waze2.getcdn.link` → HTTP
   `get-route-console:8080`. Zero Trust › Access › Applications: protect
   `waze2.getcdn.link` with path `admin*`, as for `waze`.
2. **A key for GET.ride on the NAS console.** At
   `https://waze2.getcdn.link/admin` › **Apps**: create `GET.ride fares
   (waze2)` and copy its key.
3. **GET.ride's second Waze server.** Admin › Settings › Fare AI provider ›
   Waze servers › **Add**: `https://waze2.getcdn.link` with that key, below
   `waze.getcdn.link`. **Test**, **Save changes**.
4. **waze off the NAS.** In GET.route's (the NAS's) tunnel, delete the
   public hostname `waze.getcdn.link`. In the `getcdn.link` zone › DNS,
   delete the `waze` record if it is still there.
5. **waze on the Mac.** In the `GET.route Mac` tunnel › Public hostnames ›
   **Add**: `waze.getcdn.link` → HTTP `localhost:8200`. The Access
   application for `waze.getcdn.link/admin*` stays as it is.
6. **GET.ride's first Waze server.** On the `https://waze.getcdn.link` card,
   **Change** the key to the Mac console's GET.ride key (step 6.3). **Test**,
   **Save changes**.
7. **The NAS console's order.** At `https://waze2.getcdn.link/admin` ›
   **Servers**: **Ask earlier** on the NAS pool so it is first, the Mac
   second. Under **Apps**, revoke the old `GET.ride fares` key (GET.ride no
   longer uses it).

## Check it

- `https://waze.getcdn.link/health` and `https://waze2.getcdn.link/health`
  both answer `"status":"ok"`.
- A fare in GET.ride shows in the Mac console's **Request log**
  (`waze.getcdn.link/admin`), answered by the Mac pool.
- Logs: `~/get.route/console/deploy/mac/logs/console.log`.
- Update: `cd ~/get.route && git pull && console/.venv/bin/pip install -q -r console/requirements.txt`,
  then `launchctl kickstart -k gui/$(id -u)/com.getride.getroute-console`.
- Back up `~/get.route/console/deploy/mac/data/` with `.env` next to it
  (Time Machine covers both); without `WZ_SECRET_KEY` the servers' keys in
  the database can't be read.
