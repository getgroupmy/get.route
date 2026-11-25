# GET.route on a Mac mini (Apple chip), with the NAS as the fallback

The Mac mini answers Waze lookups first; the NAS pool (`../nas`) stays as it
is and answers when the Mac doesn't. The GET.route console
(`console/`, `waze.getcdn.link`) on the NAS asks them in that order:

```
 GET.ride ──X-Route-Key──► waze.getcdn.link ──┬─► Mac mini: pool (http://MAC_IP:8100) ─► workers 8101…8104 (Chrome)
 (and other apps)        (console, on the NAS) └─► NAS: get-route-pool ─► get-route-01…16 (fallback)
```

**Why not Docker on the Mac?** The Waze image is Intel-only (it ships Google
Chrome for Linux x86-64). On an Apple chip Docker would run Chrome through
Intel emulation: slow, and Chrome under emulation crashes. On macOS itself
GET.route uses the Mac's own Google Chrome in a real window, which is
faster and is what Waze scores best.

**How the fallback works.** For each call the console asks the Mac first,
within the Mac's time (3 s by default, set on its card in the console). A
server that doesn't answer, or answers with a failure, rests (60 s by
default); while the Mac rests, calls go straight to the NAS, and the Mac is
asked again when its rest ends. The console checks both every minute, and
GET.ride's own health check watches the console.

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

6. Reach it from the GET.route console (`console/`, `waze.getcdn.link`) on
   the NAS. Keep `POOL_HOST=0.0.0.0` in `.env` so the dispatcher answers on
   the office network (the workers stay on this Mac only), and give the Mac a
   fixed address on the office router (a DHCP reservation). In the console,
   **Servers › Add a server**: `http://MAC_IP:8100` with this Mac's
   `ROUTE_API_KEY`, then **Ask earlier** until it is above the NAS pool, and
   **Test**.

   macOS's firewall, if it is on, asks once whether Python may accept
   incoming connections: Allow.

7. Your apps then call the console, not this Mac: in GET.ride, **Admin ›
   Settings › Fare AI provider › Waze servers** has one server,
   `https://waze.getcdn.link`, with GET.ride's key from the console's
   **Apps** tab.

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
