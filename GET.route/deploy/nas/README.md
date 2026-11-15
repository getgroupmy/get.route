# GET.route on the office NAS

GET.route answers GET.ride's Fare AI with Waze's live route: real distance,
traffic-aware time and tolls. The compose file runs **three containers**
(`get-route-1` to `-3`), each one "Waze server" in **Admin › Settings ›
Fare AI provider**.

```
                                                      ┌─► get-route-1 (Chrome + API)  e.g. Selangor
 ai-route-proxy ──https──► routeN.getride.my ─ Tunnel ─┼─► get-route-2                 e.g. Kuala Lumpur
 (Supabase)      X-Route-Key                (cloudflared)└─► get-route-3                 e.g. all regions
```

**Splitting the load by area.** In Admin, give each server an area: a
country, state, city or suburb from Admin › Country / States / Cities. For
each trip GET.ride finds the pickup's area the same way commission rules
do, then asks:

1. the server with the most specific matching area (suburb, then city,
   state, country);
2. then servers set to **All regions**;
3. then the other areas' servers, as a backup.

A server that fails rests for the retry window set on that page, and the
next one is asked.

- **No port is opened** on the NAS or the router: `cloudflared` makes an
  outgoing connection and Cloudflare sends the hostname down it.
- Every call except `/health` needs the secret header `X-Route-Key`.
- Chrome runs inside the container on the office connection. Waze scores
  the tokens it makes; an office or home connection scores far better than
  a cloud server, which is why this runs here.
- Each container makes about 25 Waze calls a minute (each token serves ~5
  calls), so three give about 75. A trip with stops costs one call per leg.
  To add a container, copy a `get-route-N` block in `docker-compose.yml`
  and add its hostname to the tunnel.

## What the NAS needs

- Synology DSM 7.2+ with **Container Manager**, x86-64 (the Chrome image
  is amd64 only).
- About 1.5 GB of memory per container (capped at 2 GB each, so 6 GB for
  three) and 3 GB of disk for the image, which all containers share. On the
  DS224+ (18 GB) this fits beside the OSRM maps (about 5 GB).
- A Cloudflare account with the `getride.my` zone.

## Set it up

1. Copy this repository's `GET.route` folder to the NAS, e.g.
   `/volume1/docker/get-route`.
2. In Cloudflare Zero Trust › Networks › Tunnels, create a tunnel
   (Docker). Copy the token. Add one public hostname per container:
   `route1.getride.my` → `http://get-route-1:8000`, `route2.getride.my` →
   `http://get-route-2:8000`, `route3.getride.my` → `http://get-route-3:8000`.
3. In `deploy/nas`, copy `.env.example` to `.env`; set `TUNNEL_TOKEN` and
   `ROUTE_API_KEY` (`openssl rand -hex 32`).
4. Start it: Container Manager › Project › Create, path
   `deploy/nas`, or over SSH:

   ```bash
   cd /volume1/docker/get-route/deploy/nas && sudo docker compose up -d --build
   ```

5. Check each from anywhere: `https://route1.getride.my/health` answers
   `{"status": "ok", ...}`.
6. In GET.ride, **Admin › Settings › Fare AI provider**: set the data
   source to **Waze (GET.route)**. Add one server per container with its
   URL and the key, tap **Change** to give it an area (or leave it on All
   regions), tap **Test**, then **Save changes**. Choose what happens when
   every server fails: ask the AI instead, or no estimate.

The first fare request opens Chrome inside the container (about 20–40 s);
after that answers take about 1–3 s. Chrome closes after 10 idle minutes
and opens again on the next request.
