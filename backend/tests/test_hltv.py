from __future__ import annotations

import threading
import time

import app.hltv.client as client
from app.config import get_settings
from app.hltv.client import (
    _match_involves_team,
    _parse_match_teams,
    _select_dem_members,
    map_from_filename,
)


def test_map_from_filename_reads_map_or_none():
    assert map_from_filename("esl-faze-vs-navi-mirage.dem") == "de_mirage"
    assert map_from_filename("blast-g2-vs-vitality-de_nuke.dem") == "de_nuke"
    assert map_from_filename("grand-final-spirit-vs-faze-m3.dem") is None  # no map name


def test_select_dem_members_filters_by_map():
    members = [
        "faze-vs-navi-mirage.dem",
        "faze-vs-navi-m2-inferno.dem",
        "faze-vs-navi-m3.dem", 
        "readme.txt",
    ]
    assert _select_dem_members(members, None) == members[:3]  # all .dem, no junk
    assert _select_dem_members(members, "de_mirage") == ["faze-vs-navi-mirage.dem"]
    assert _select_dem_members(members, "de_inferno") == ["faze-vs-navi-m2-inferno.dem"]
    assert _select_dem_members(members, "de_nuke") == []


def test_match_involves_team_matches_team_link():
    html = '<a href="/team/12591/koi">KOI</a> vs <a href="/team/9999/x">X</a>'
    assert _match_involves_team(html, "12591")
    assert _match_involves_team(html, "9999")


def test_match_involves_team_rejects_other_team():
    # An OG (10503) match must not be accepted when KOI (12591) was requested.
    og = '<a href="/team/10503/og">OG</a> vs <a href="/team/8888/y">Y</a>'
    assert not _match_involves_team(og, "12591")


def test_match_involves_team_accepts_stats_url_form():
    assert _match_involves_team("...?team=12591&map=...", "12591")


def test_parse_match_teams_reads_both_teams():
    # Each team logo anchor is followed by its teamName div; a sidebar /team/
    # link without a teamName must be ignored.
    html = (
        '<a href="/team/4608/natus-vincere" class="team1"><img class="logo"></a>'
        '<div class="teamName">Natus Vincere</div>'
        '<a href="/team/6667/faze"><img class="logo"></a>'
        '<div class="teamName">FaZe</div>'
        '<a href="/team/9999/other-match-team">Other</a>'
    )
    assert _parse_match_teams(html) == [("4608", "Natus Vincere"), ("6667", "FaZe")]


def test_parse_match_teams_empty_when_no_team_names():
    assert _parse_match_teams('<a href="/team/1/x">X</a> vs <a href="/team/2/y">Y</a>') == []


class _FakeResp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"status": "ok", "solution": {"response": "<html></html>"}}


def _run_concurrent_solves(monkeypatch, *, limit: int, threads: int) -> int:
    """Drive ``threads`` solves through a gate of ``limit`` and return peak overlap."""
    monkeypatch.setattr(get_settings(), "flaresolverr_url", "http://fake:8191")

    active = 0
    peak = 0
    state = threading.Lock()

    def fake_post(url, json=None, timeout=None):
        nonlocal active, peak
        with state:
            active += 1
            peak = max(peak, active)
        time.sleep(0.1)
        with state:
            active -= 1
        return _FakeResp()

    monkeypatch.setattr(client, "_gate", threading.Semaphore(limit))
    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    try:
        workers = [threading.Thread(target=client._flaresolverr_get, args=("http://hltv",)) for _ in range(threads)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
    finally:
        client._gate = None  # let later callers rebuild from settings
    return peak


def test_flaresolverr_serializes_to_one_by_default(monkeypatch):
    # The default single solver must never run two solves at once.
    assert _run_concurrent_solves(monkeypatch, limit=1, threads=4) == 1


def test_flaresolverr_allows_configured_parallelism(monkeypatch):
    # A higher limit lets overlapping jobs solve in parallel.
    assert _run_concurrent_solves(monkeypatch, limit=3, threads=5) > 1
