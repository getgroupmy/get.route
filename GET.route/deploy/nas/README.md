# GET.route on the office NAS

GET.route answers GET.ride's Fare AI with Waze's live route: real distance,
traffic-aware time and tolls. The compose file runs **16 containers, one
per Malaysian state and federal territory** (`get-route-johor` …
`get-route-putrajaya`), each one "Waze server" in **Admin › Settings ›
Fare AI provider**.

```
                                                          ┌─► get-route-johor     (Chrome + API)
 ai-route-proxy ──https──► route-<state>.getride.my ─ Tunnel ─┼─► get-route-selangor
 (Supabase)      X-Route-Key                    (cloudflared) ├─► …
                                                          └─► get-route-putrajaya
```

**Splitting the load by state.** In Admin, give each server its state as
its area. For each trip GET.ride finds the pickup's state the same way
commission rules do (from the state outlines mapped in Admin › Country /
States / Cities), then asks:

1. the server for the pickup's state (or a more specific area, if you
   give any server a city or suburb);
2. then servers set to **All regions**, if any;
3. then the other states' servers, as a backup.

A server that fails rests for the retry window set on that page, and the
next one is asked. A pickup in a state with no mapped outline has no state
to match, so it goes straight to the backups: map all 16 outlines.

- **No port is opened** on the NAS or the router: `cloudflared` makes an
  outgoing connection and Cloudflare sends each hostname down it.
- Every call except `/health` needs the secret header `X-Route-Key`.
- Chrome runs inside each container on the office connection. Waze scores
  the tokens it makes; an office or home connection scores far better than
  a cloud server, which is why this runs here.
- Each container makes about 25 Waze calls a minute (each token serves ~5
  calls), so 16 give about 400 in all, but a state gets only its own
  container's 25 before the backups are used. A trip with stops costs one
  call per leg.
- Every minute GET.ride checks each server; Fare AI admins get a push when
  one has been down for 5 minutes, and when it is back.

## What the NAS needs

- Synology DSM 7.2+ with **Container Manager**, x86-64 (the Chrome image
  is amd64 only).
- 3 GB of disk for the image, which all 16 containers share.
- A Cloudflare account with the `getride.my` zone.

### Memory

Each container is capped at 1 GB (`MEM_PER_SERVER`), so 16 can use up to
16 GB. They will not all use it at once: Chrome closes after 10 idle
minutes, so containers for quiet states stay small. **These are estimates;
nothing has been measured on the NAS yet.**

The DS224+ has 18 GB (its built-in 2 GB plus one 16 GB module), which is
the most it can take, so memory cannot be added. DSM, the OSRM maps (about
5 GB) and the face match server already use part of it; on a 1 GB cap per
container, roughly 11 of the 16 can be at full size at once, which is
enough when not every state is busy together. Check how much is free in
Resource Monitor before starting them, then watch Container Manager through
a busy day:

- A container that runs out of memory is stopped and restarts by itself
  (`restart: unless-stopped`); meanwhile its trips go to the backup servers,
  and the admins get the offline push if it stays down 5 minutes.
- If that keeps happening, or fares slow down at peak (the 4-core Celeron
  J4125 also runs every Chrome window), move the quietest states to a
  second machine on an office or home connection: copy this folder there,
  keep only those states in `docker-compose.yml`, and give it its own
  tunnel.

## Set it up

1. Copy this repository's `GET.route` folder to the NAS, e.g.
   `/volume1/docker/get-route`.
2. In Cloudflare Zero Trust › Networks › Tunnels, create a tunnel
   (Docker). Copy the token. Add one public hostname per container, as
   listed at the top of `docker-compose.yml`, e.g.
   `route-johor.getride.my` → `http://get-route-johor:8000`.
3. In `deploy/nas`, copy `.env.example` to `.env`; set `TUNNEL_TOKEN` and
   `ROUTE_API_KEY` (`openssl rand -hex 32`). All 16 containers share the key.
4. Start it: Container Manager › Project › Create, path
   `deploy/nas`, or over SSH:

   ```bash
   cd /volume1/docker/get-route/deploy/nas && sudo docker compose up -d --build
   ```

5. Check each from anywhere: `https://route-johor.getride.my/health`
   answers `{"status": "ok", ...}`.
6. In GET.ride, **Admin › Settings › Fare AI provider**: set the data
   source to **Waze (GET.route)**. Add 16 servers, one per container,
   each with its URL and the key; tap **Change** and pick Malaysia and its
   state; tap **Test**; then **Save changes**. Choose what happens when
   every server fails: ask the AI instead, or no estimate.

The first fare request opens Chrome inside the container (about 20–40 s);
after that answers take about 1–3 s. Chrome closes after 10 idle minutes
and opens again on the next request.
