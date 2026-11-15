"""Parsing checks that need no browser: python -m pytest test_traffic_scraper.py"""
import pytest

from TrafficScraper import parse_route_total, with_english


@pytest.mark.parametrize("text, expected", [
    ("via Jalan Tun Razak 35 min (12.3 km) Fastest route", (35, 12.3)),
    ("via E2 3 hr 45 min (350 km) Turn left 2 min (800 m)", (225, 350.0)),
    ("via E1 2 hr (180 km)", (120, 180.0)),
    ("3 h 45 min (350 km)", (225, 350.0)),
    ("1 day 2 hr (1,900 km)", (1560, 1900.0)),
    ("2 days 1 hr (3,100 km)", (2940, 3100.0)),
    ("E12 35 min (12 km)", (35, 12.0)),               # road code must not fuse
    ("Head north 4 min (900 m)", (4, 0.9)),
    ("via E1 20 hr 5 min (1,234 km)", (1205, 1234.0)),
    ("via MEX 25 min (24.1 km) Continue 1 min (450 m) Take exit 3 min (2.1 km)", (25, 24.1)),
    ("melalui E2 35 min (12.3 km)", (35, 12.3)),
    ("Toll road (12 km) via MEX 25 min (24.1 km)", (25, 24.1)),  # a bare distance is skipped
    ("10 mins (5 km)", (10, 5.0)),
])
def test_reads_the_route_total(text, expected):
    assert parse_route_total(text) == expected


@pytest.mark.parametrize("text", [
    "Toll road (12 km)",                 # no time at all
    "35 Min. (12,3 km)",                 # decimal comma: not an English page
    "3 Std. 45 min (350 km)",            # an hour unit it can't read: refuse, don't drop the hours
    "",
])
def test_refuses_what_it_cannot_fully_read(text):
    with pytest.raises(ValueError):
        parse_route_total(text)


def test_with_english_adds_hl_and_keeps_the_rest():
    url = "https://www.google.com/maps/dir/A/B/data=!3e0?authuser=0&g_ep=EgoyMDI1MDQyMy4wIKXMDSoASAFQAw%3D%3D"
    assert with_english(url) == url + "&hl=en"
    assert with_english("https://www.google.com/maps/dir/3.158,101.712/3.134,101.686/") == \
        "https://www.google.com/maps/dir/3.158,101.712/3.134,101.686/?hl=en"
    assert with_english("https://www.google.com/maps/dir/A/B?hl=ms&x=1") == \
        "https://www.google.com/maps/dir/A/B?x=1&hl=en"
