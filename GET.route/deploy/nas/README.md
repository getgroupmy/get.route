# GET.route on the office NAS

GET.route answers GET.ride's Fare AI with Waze's live route: real distance,
traffic-aware time and tolls. Each copy you run is one "Waze server" in
**Admin › Settings › Fare AI provider**; GET.ride tries them in the order
listed and skips one that fails for the retry window set there.

```
 ai-route-proxy ──https──► route1.getride.my ──► Cloudflare Tunnel ──► get-route (Chrome + API)
 (Supabase)      X-Route-Key                     (cloudflared, outgoing only)
```

- **No port is opened** on the NAS or the router: `cloudflared` makes an
  outgoing connection and Cloudflare sends the hostname down it.
- Every call except `/health` needs the secret header `X-Route-Key`.
- Chrome runs inside the container on the office connection. Waze scores
  the tokens it makes; an office or home connection scores far better than
  a cloud server, which is why this runs here.
- One copy makes about 25 Waze calls a minute (each token serves ~5 calls).
  A trip with stops costs one call per leg. Add more copies on other
  machines or connections as more Waze servers if you need more.

## What the NAS needs

- Synology DSM 7.2+ with **Container Manager**, x86-64 (the Chrome image
  is amd64 only).
- About 1.5 GB of memory (capped at 2 GB) and 3 GB of disk for the image.
- A Cloudflare account with the `getride.my` zone.

## Set it up

1. Copy this repository's `GET.route` folder to the NAS, e.g.
   `/volume1/docker/get-route`.
2. In Cloudflare Zero Trust › Networks › Tunnels, create a tunnel
   (Docker). Copy the token. Add a public hostname, e.g.
   `route1.getride.my`, service `http://get-route:8000`.
3. In `deploy/nas`, copy `.env.example` to `.env`; set `TUNNEL_TOKEN` and
   `ROUTE_API_KEY` (`openssl rand -hex 32`).
4. Start it: Container Manager › Project › Create, path
   `deploy/nas`, or over SSH:

   ```bash
   cd /volume1/docker/get-route/deploy/nas && sudo docker compose up -d --build
   ```

5. Check it from anywhere: `https://route1.getride.my/health` answers
   `{"status": "ok", ...}`.
6. In GET.ride, **Admin › Settings › Fare AI provider**: set the data
   source to **Waze (GET.route)**, add a server with the URL
   `https://route1.getride.my` and the same key, save, then tap **Test**.

The first fare request opens Chrome inside the container (about 20–40 s);
after that answers take about 1–3 s. Chrome closes after 10 idle minutes
and opens again on the next request.
