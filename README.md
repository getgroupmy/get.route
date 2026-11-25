# GET.route

The route servers behind GET.ride's fare estimates, run on the office NAS.

| Folder | What it is |
|---|---|
| [`GET.route/`](GET.route/README.md) | **Waze**: live traffic, distance and tolls from the Waze live map. A pool of 16 containers behind one dispatcher, on the NAS. The full guide, endpoints and settings are in its README. |
| [`GET.route/deploy/nas/`](GET.route/deploy/nas/README.md) | Running the pool on the office NAS: compose file, tunnel, `.env`, updates and checks. |
| [`GET.route/deploy/mac/`](GET.route/deploy/mac/README.md) | Running it on a Mac mini (Apple chip) as the first Waze server, with the NAS as the fallback. |
| [`console/`](console/README.md) | **The GET.route console, the only thing apps call**: `waze.getcdn.link` on the Mac mini (`console/deploy/mac`) and `waze2.getcdn.link` on the NAS. One standalone service for GET's own apps, with a key per app, the Waze servers in order with failover, a request log, and an admin console (sign-in, roles, audit trail) as on GET.ekyc. |
| [`Traffic-Scraper/`](Traffic-Scraper/) | A copy of Traffic-Scraper (Google Maps drive time and distance) with fixes and tests. GET.ride's Google Maps step runs from getgroupmy/get.route.backup. |

```
                 ┌─► waze.getcdn.link  (console, Mac mini) ──┬─► Mac pool  (GET.route/deploy/mac)  first
 GET.ride ───────┤                                           └─► NAS pool                         second
 other apps      └─► waze2.getcdn.link (console, NAS)      ──┬─► NAS pool  (GET.route/deploy/nas)  first
 (X-Route-Key)                                               └─► Mac pool                         second
```

Apps never call a Waze server directly: each has its own key from each
console, and lists `waze.getcdn.link` first and `waze2.getcdn.link` second,
so Waze keeps working when either machine is down.

GET.ride sets its side in **Admin › Settings › Fare AI provider**: the fare
data order (e.g. Waze, then Google Maps, then Apple Maps, then AI, then
OSRM), each step's servers and keys, the Waze / Google Maps / Apple Maps
balance, and the **Time limits** (Waze 3 s; the rider app waits 8 s in all).
Its Waze servers are `https://waze.getcdn.link` and
`https://waze2.getcdn.link`, each with GET.ride's key from that console.

Apple Maps comes from getgroupmy/get.route.apple (Apple's official Maps
Server API).
