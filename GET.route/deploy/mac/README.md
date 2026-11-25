# GET.route on a Mac mini (Apple chip), with the NAS as the fallback

The Mac mini answers GET.ride's Waze lookups first; the NAS pool
(`../nas`) stays as it is and answers when the Mac doesn't. GET.ride lists
both as Waze servers, the Mac first:

```
                                 ┌─► route-mac.getride.my ─ Tunnel ─► Mac mini: pool (8100) ─► workers 8101…8104 (Chrome)
 ai-route-proxy ──X-Route-Key──┤
 (GET.ride)                      └─► route.getride.my ───── Tunnel ─► NAS: get-route-pool ─► get-route-01…16 (fallback)
```

**Why not Docker on the Mac?** The Waze image is Intel-only (it ships Google
Chrome for Linux x86-64). On an Apple chip Docker would run Chrome through
Intel emulation: slow, and Chrome under emulation crashes. On macOS itself
GET.route uses the Mac's own Google Chrome in a real window, which is
faster and is what Waze scores best.

**How the fallback works.** For each fare GET.ride asks the Mac first, within
Waze's time (Admin › Fare AI provider › Time limits, 3 s). A server that
fails rests for the retry time set on the same page; while the Mac rests,
fares go straight to the NAS, and the Mac is asked again when its rest ends.
The minute-by-minute health check watches both and tells Fare AI admins when
one has been offline for 5 minutes.

**What the fallback does not cover.** The Mac and the NAS share the office's
Unifi line and its one fixed IP address. If Waze ever refuses that address,
it refuses both; the fare order's later steps (Apple Maps, the AI, OSRM)
cover that case.

## What it needs

- A Mac mini with an Apple chip, macOS 14 or later, on the office network.
- [Google Chrome](https://www.google.com/chrome/) in Applications.
- Python 3.11 or later: `brew install python@3.12` (Homebrew) or
  python.org.
- A user account that stays logged in: Waze needs a real, visible Chrome,
  which needs a logged-in screen. The Mac can sit with its screen off.

### Mac settings

- **System Settings › Energy** (or Battery › Options): **Prevent automatic
  sleeping when the display is off** on; **Start up automatically after a
  power failure** on; **Wake for network access** on.
- **System Settings › Users & Groups › Automatically log in as** this user
  (turn FileVault off if macOS won't offer it), so a restart comes back to a
  logged-in screen.
- **System Settings › Lock Screen**: **Start Screen Saver when inactive** and
  **Require password after screen saver** set to never/off. A locked screen
  is fine for Chrome, but auto login is what matters after a restart.

## Set it up

1. Get the code (Terminal):

   ```bash
   cd ~ && git clone https://github.com/getgroupmy/get.route.git
   ```

2. Create its Python environment and install the parts:

   ```bash
   cd ~/get.route/GET.route && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```

3. Settings: copy `.env.example` to `.env` and set `ROUTE_API_KEY` to a new
   key for the Mac:

   ```bash
   cd ~/get.route/GET.route/deploy/mac && cp .env.example .env && openssl rand -hex 32
   ```

   Paste the printed key after `ROUTE_API_KEY=` in `.env` (TextEdit or
   `nano .env`). `WORKERS=4` serves about 90 Waze calls a minute; raise it
   if the Mac has memory to spare (each open Chrome takes 0.4–1 GB).

4. Try it once by hand:

   ```bash
   ~/get.route/GET.route/deploy/mac/start.sh
   ```

   In a second Terminal window:

   ```bash
   curl -s -H "X-Route-Key: $(grep ROUTE_API_KEY ~/get.route/GET.route/deploy/mac/.env | cut -d= -f2)" "http://127.0.0.1:8100/routes/search?from=3.158,101.712&to=3.134,101.686&max_routes=1" | head -c 300
   ```

   The first call opens a Chrome window and takes 20–40 s; leave it open.
   macOS may ask whether Python may accept incoming connections: Allow.
   Stop the script with Ctrl+C.

5. Start it at login, and again if it stops: copy the launchd file, put your
   own folder in it, and load it.

   ```bash
   sed "s|/Users/YOU/get.route|$HOME/get.route|g" ~/get.route/GET.route/deploy/mac/com.getride.getroute.plist > ~/Library/LaunchAgents/com.getride.getroute.plist
   ```

   ```bash
   launchctl load -w ~/Library/LaunchAgents/com.getride.getroute.plist
   ```

6. The tunnel: in Cloudflare Zero Trust › Networks › Tunnels, create a new
   tunnel (macOS) for the Mac and copy its token. Add one public hostname:
   `route-mac.getride.my` → `http://localhost:8100`. Then on the Mac:

   ```bash
   brew install cloudflared
   ```

   ```bash
   sudo cloudflared service install PASTE_THE_TUNNEL_TOKEN
   ```

   It runs as a system service, starts on boot and needs no login.

   GET.ride's subdomain worker answers every `*.getride.my` name with the
   web app unless the name is in its pass-through list, so `route-mac` must
   be there too: in `wrangler.toml` (getgroupmy/get-ride) and, when it is
   set, in the repository variable `SUBDOMAIN_PROXY_PASS_THROUGH`, then the
   worker deployed. Until then `https://route-mac.getride.my/health` shows the
   web page instead of `{"status": "ok", "pool": 4}`.

7. In GET.ride, **Admin › Settings › Fare AI provider › Waze servers**: add
   a server `https://route-mac.getride.my` with the Mac's key and tap
   **Test**. Servers are asked in order, so tap its **Ask earlier** arrow
   until it is above the NAS's `https://route.getride.my`. **Save changes.**

## Check and update

- Logs: `~/get.route/GET.route/deploy/mac/logs/` (one file per worker,
  `pool.log`, `launchd.log`).

  ```bash
  tail -n 5 ~/get.route/GET.route/deploy/mac/logs/pool.log
  ```

  It starts with `GET.route pool: 4 containers, next after 23/min, warm at
  10, keeping 1 warm every 240 s`.
- Chrome in worker 1 (`"chrome": "open"` is what keep-warm holds it at):

  ```bash
  curl -s -H "X-Route-Key: $(grep ROUTE_API_KEY ~/get.route/GET.route/deploy/mac/.env | cut -d= -f2)" http://127.0.0.1:8101/health
  ```

- Update to the latest code and restart:

  ```bash
  cd ~/get.route && git pull && GET.route/.venv/bin/pip install -q -r GET.route/requirements.txt
  ```

  ```bash
  launchctl kickstart -k gui/$(id -u)/com.getride.getroute
  ```

- Stop it for good: `launchctl unload -w
  ~/Library/LaunchAgents/com.getride.getroute.plist`. GET.ride then uses the
  NAS by itself.
