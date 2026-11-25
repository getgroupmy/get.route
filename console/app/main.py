"""GET.route console: one standalone service in front of the Waze servers.

Your apps call it at WZ_PUBLIC_URL (e.g. https://waze.getcdn.link) with their
own key, on GET.route's own paths; it asks the Waze servers in the console's
order (the Mac mini first, the NAS pool behind it) and keeps a request log.
The console at /admin manages API clients, servers, settings, console users
and the audit trail."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

from . import health, proxy
from .config import get_settings
from .db import init_db
from .routers import admin, api, session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()  # fail fast on bad configuration
    init_db()
    health.start()
    yield
    health.stop()
    proxy.reset_http()


app = FastAPI(title="GET.route console", version="1.0.0", lifespan=lifespan,
              description="Waze routes, jams, alerts and places for GET's own apps, from the office Waze servers.")
app.include_router(api.router)
app.include_router(session.router)
app.include_router(admin.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/admin")


@app.get("/admin", include_in_schema=False)
def admin_ui():
    return FileResponse(STATIC / "admin.html", headers={
        "Cache-Control": "no-store",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                   "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
    })
