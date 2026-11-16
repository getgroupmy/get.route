"""Which GET.route container takes the next query: the rules of the pool
dispatcher (pool_server.py), kept free of I/O so they can be tested exactly.

The containers stand in a fixed order (1, 2, 3 ...). Each query goes to the
first container that has served fewer than SWITCH_AT queries in the last 60
seconds and is not resting after a failure. So container 1 carries the
traffic alone until its 23rd query of the minute; the 24th goes to
container 2, and so on. As the minute rolls on, traffic falls back to
container 1 by itself.

Each container's Chrome mints a reCAPTCHA token that serves ~5 calls and
mints about 5 a minute, so ~25 calls a minute; 23 leaves a margin.

A cold container needs 20-40 s to open Chrome, so the next container is
warmed ahead of time: when a container serves its WARM_AT-th query within
the minute (10 by default), the one after it is told to open Chrome. A
container that failed (no answer, 5xx, refused key) rests for REST_SECONDS
and the query is retried on the next one.

Between fares the first container(s) are kept warm (keep_warm_targets):
pool_server.py asks them to open Chrome every few minutes, well inside the
containers' 10 idle minutes, so a quiet day's fares don't each meet a cold
container (20-40 s, longer than GET.ride waits). Warming spends no Waze call.
"""
import threading
import time
from collections import deque

WINDOW_SECONDS = 60


class Pool:
    def __init__(self, urls, switch_at=23, warm_at=10, rest_seconds=60, warm_every=60):
        if not urls:
            raise ValueError("the pool needs at least one container")
        if not 0 < warm_at <= switch_at:
            raise ValueError("warm_at must be between 1 and switch_at")
        self.urls = list(urls)
        self.switch_at = switch_at
        self.warm_at = warm_at
        self.rest_seconds = rest_seconds
        self.warm_every = warm_every          # don't ask the same container to warm more often
        self._calls = [deque() for _ in self.urls]
        self._resting_until = [0.0] * len(self.urls)
        self._last_error = [None] * len(self.urls)
        self._warmed_at = [None] * len(self.urls)
        self._lock = threading.Lock()

    def _trim(self, i, now):
        q = self._calls[i]
        while q and q[0] <= now - WINDOW_SECONDS:
            q.popleft()

    def calls_last_minute(self, i, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            self._trim(i, now)
            return len(self._calls[i])

    def take(self, now=None, skip=()):
        """Reserve the next query: (container index, index to warm or None).
        (None, None) when every container is full or resting. `skip` lists
        containers already tried for this query."""
        now = time.monotonic() if now is None else now
        with self._lock:
            chosen = None
            for i in range(len(self.urls)):
                if i in skip or self._resting_until[i] > now:
                    continue
                self._trim(i, now)
                if len(self._calls[i]) < self.switch_at:
                    chosen = i
                    break
            if chosen is None:
                return None, None
            self._calls[chosen].append(now)
            warm = None
            if len(self._calls[chosen]) >= self.warm_at:
                warm = self._next_to_warm(chosen, now)
            return chosen, warm

    def _next_to_warm(self, i, now):
        for j in range(i + 1, len(self.urls)):
            if self._resting_until[j] > now:
                continue
            last = self._warmed_at[j]
            if last is not None and now - last < self.warm_every:
                return None
            self._warmed_at[j] = now
            return j
        return None

    def keep_warm_targets(self, n, now=None):
        """The first [n] containers that are not resting: the ones traffic
        reaches first, so their Chrome is kept open between fares. A resting
        container is passed over for the next one."""
        now = time.monotonic() if now is None else now
        with self._lock:
            return [i for i in range(len(self.urls)) if self._resting_until[i] <= now][:max(0, n)]

    def failed(self, i, error, now=None):
        """Container i did not answer usefully: rest it and keep the reason."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._resting_until[i] = now + self.rest_seconds
            self._last_error[i] = str(error)[:200]

    def succeeded(self, i):
        with self._lock:
            self._resting_until[i] = 0.0
            self._last_error[i] = None

    def status(self, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            out = []
            for i, url in enumerate(self.urls):
                self._trim(i, now)
                out.append({
                    "container": i + 1,
                    "url": url,
                    "calls_last_minute": len(self._calls[i]),
                    "resting_seconds": max(0, round(self._resting_until[i] - now)),
                    "last_error": self._last_error[i],
                })
            return out
