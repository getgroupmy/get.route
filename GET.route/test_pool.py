import pytest

from pool import Pool

URLS = [f"http://get-route-{i:02d}:8000" for i in range(1, 17)]


def fill(pool, n, now=0.0):
    return [pool.take(now=now) for _ in range(n)]


def test_container_1_alone_until_its_23rd_query():
    p = Pool(URLS)
    picks = fill(p, 23)
    assert {c for c, _ in picks} == {0}
    assert p.take(now=0.0)[0] == 1          # the 24th goes to container 2


def test_next_container_warmed_at_the_10th_query_once():
    p = Pool(URLS)
    picks = fill(p, 23)
    warms = [(n + 1, w) for n, (_, w) in enumerate(picks) if w is not None]
    assert warms == [(10, 1)]               # 10th query warms container 2, only once


def test_spill_chain_and_its_warm_ups():
    p = Pool(URLS)
    picks = fill(p, 23 * 3)
    assert [c for c, _ in picks[23:46]] == [1] * 23
    assert [c for c, _ in picks[46:]] == [2] * 23
    assert [w for _, w in picks if w is not None] == [1, 2, 3]


def test_traffic_falls_back_to_container_1_as_the_minute_rolls():
    p = Pool(URLS)
    fill(p, 23, now=0.0)
    assert p.take(now=30.0)[0] == 1
    assert p.take(now=60.5)[0] == 0         # the first 23 have left the window


def test_a_failed_container_rests_and_the_query_moves_on():
    p = Pool(URLS, rest_seconds=60)
    c, _ = p.take(now=0.0)
    p.failed(c, "HTTP 502", now=0.0)
    assert p.take(now=1.0, skip={c})[0] == 1
    assert p.take(now=2.0)[0] == 1          # container 1 still resting
    assert p.take(now=61.0)[0] == 0         # back after the rest
    p.succeeded(0)
    assert p.status(now=61.0)[0]["last_error"] is None


def test_everything_full_or_resting():
    p = Pool(URLS[:2], switch_at=2, warm_at=1)
    fill(p, 4)
    assert p.take(now=0.0) == (None, None)


def test_warm_skips_resting_and_last_container_has_no_next():
    p = Pool(URLS[:3], switch_at=23, warm_at=10)
    p.failed(1, "down", now=0.0)
    picks = fill(p, 10)
    assert picks[-1] == (0, 2)              # container 2 resting: warm container 3
    p2 = Pool(URLS[:1])
    assert fill(p2, 10)[-1] == (0, None)


def test_bad_settings():
    with pytest.raises(ValueError):
        Pool([])
    with pytest.raises(ValueError):
        Pool(URLS, switch_at=10, warm_at=11)
