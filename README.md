# GET.route

The route servers behind GET.ride's fare estimates, run on the office NAS.

| Folder | What it is |
|---|---|
| [`GET.route/`](GET.route/README.md) | **Waze**: live traffic, distance and tolls from the Waze live map. A pool of 16 containers behind one dispatcher, at `https://route.getride.my`. The full guide, endpoints and settings are in its README. |
| [`GET.route/deploy/nas/`](GET.route/deploy/nas/README.md) | Running the pool on the office NAS: compose file, tunnel, `.env`, updates and checks. |
| [`Traffic-Scraper/`](Traffic-Scraper/) | A copy of Traffic-Scraper (Google Maps drive time and distance) with fixes and tests. GET.ride's Google Maps step runs from getgroupmy/get.route.backup. |

GET.ride asks these through **Admin › Settings › Fare AI provider**: the
fare data order (e.g. Waze, then Google Maps, then Apple Maps, then AI, then
OSRM), each step's server cards and keys, the Waze / Google Maps / Apple
Maps balance, and the **Time limits** (Waze 2 s by default; the rider app
waits 7 s in all).

Apple Maps comes from getgroupmy/get.route.apple (Apple's official Maps
Server API).
