from __future__ import annotations

import threading
import time
from datetime import UTC, date, datetime, timedelta

import app.hltv.client as client
from app.config import get_settings
from app.domain.enums import DateRange
from app.hltv.client import (
    _match_involves_team,
    _parse_match_meta,
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


def _unix_ms(d: date) -> str:
    return str(int(datetime(d.year, d.month, d.day, 12, tzinfo=UTC).timestamp() * 1000))


def _match_page(*, played: date, upcoming: date, header: bool = True) -> str:
    head = (
        '<div class="timeAndEvent">'
        f'<div class="time" data-time-format="HH:mm" data-unix="{_unix_ms(played)}">06:30</div>'
        f'<div class="date" data-time-format="do \'of\' MMMM y" data-unix="{_unix_ms(played)}">played</div>'
        '<div class="event text-ellipsis"><a href="/events/7907/iem-chengdu-2025">IEM Chengdu 2025</a></div>'
        "</div>"
    )
    return (
        '<div class="smartphone-top-widget-date-info">'
        f'<div class="smartphone-top-widget-date" data-unix="{_unix_ms(upcoming)}">tomorrow</div>'
        f'<div class="smartphone-top-widget-time" data-unix="{_unix_ms(upcoming)}">16:50</div></div>'
        '<a href="/events/9999/some-other-event">Some Other Event</a>'
        f'<div class="score">1 : 2</div><div class="date" data-time-format="d MMM" data-unix="{_unix_ms(played)}">8 Nov</div>'
        + (head if header else "")
        + '<td class="date"><a href="/matches/2387395/x">'
          f'<span data-time-format="d/M yy" data-unix="{_unix_ms(date(2025, 1, 2))}">2/1 25</span></a></td>'
    )


def test_parse_match_meta_skips_the_upcoming_match_widget():
    played, upcoming = date(2025, 11, 8), date.today() + timedelta(days=1)
    event, match_date = _parse_match_meta(_match_page(played=played, upcoming=upcoming))
    assert match_date == played
    assert event == "IEM Chengdu 2025"  # not the widget's "Some Other Event"


def test_parse_match_meta_falls_back_to_the_score_date():
    page = _match_page(played=date(2025, 11, 8), upcoming=date.today() + timedelta(days=1), header=False)
    assert _parse_match_meta(page)[1] == date(2025, 11, 8)


def test_parse_match_meta_drops_a_future_date():
    ahead = date.today() + timedelta(days=30)
    assert _parse_match_meta(_match_page(played=ahead, upcoming=ahead))[1] is None


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


def _drive_archives(monkeypatch, *, map_id, dems_per_match):
    """Run the archive iterator over 3 fake matches and return the reported totals"""
    from pathlib import Path

    urls = [f"http://hltv/matches/{i}/x" for i in dems_per_match]
    monkeypatch.setattr(client, "find_match_results", lambda team, rng: urls)
    monkeypatch.setattr(get_settings(), "request_delay_s", 0)
    monkeypatch.setattr(
        client,
        "_flaresolverr_get",
        lambda url, **kw: (
            '<a href="/team/1/t"><img class="logo"></a><div class="teamName">T</div>'
            '<a href="/team/2/o"><img class="logo"></a><div class="teamName">O</div>'
            '<a href="/download/demo/9">dl</a>'
        ),
    )
    monkeypatch.setattr(
        client,
        "_download_and_extract",
        lambda url, match_id, mid=None: (
            None, [Path(p) for p in dems_per_match[match_id]]
        ),
    )

    totals: list[tuple[int, int]] = []
    got = list(
        client.iter_team_demo_archives(
            "1", map_id, DateRange.LAST_3_MONTHS,
            on_totals=lambda found, expected: totals.append((found, expected)),
        )
    )
    return len(got), totals


def test_match_total_narrows_to_the_map_filter(monkeypatch):
    matches, totals = _drive_archives(
        monkeypatch,
        map_id="de_nuke",
        dems_per_match={"1": [], "2": ["b-nuke.dem"], "3": []},
    )
    assert matches == 1
    assert totals[0] == (3, 3)
    assert totals[-1] == (3, 1)
    assert matches == totals[-1][1]


def test_match_total_keeps_every_match_without_a_filter(monkeypatch):
    matches, totals = _drive_archives(
        monkeypatch,
        map_id=None,
        dems_per_match={"1": ["a.dem"], "2": ["b.dem"], "3": ["c.dem"]},
    )
    assert matches == 3
    assert totals == [(3, 3)]  # nothing dropped, no refinement


def test_download_job_is_always_public(client, monkeypatch):
    # HLTV demos feed the shared pool: a private request must not be honoured.
    from app.db import session_scope
    from app.domain.models import DownloadJob
    from app.hltv import routes as hltv_routes
    from tests.conftest import auth

    monkeypatch.setattr(hltv_routes, "_run_download_job", lambda *a, **kw: None)
    login = client.post("/auth/login", data={"username": "admin@cs2.local", "password": "admin"})
    resp = client.post(
        "/hltv/download",
        json={"team_id": "1", "team_name": "T", "visibility": "private"},
        headers=auth(login.json()["access_token"]),
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["visibility"] == "public"

    with session_scope() as session:  # shared test DB: drop the job we just made
        session.delete(session.get(DownloadJob, resp.json()["id"]))


def test_download_and_extract_cleans_workdir_on_failure(monkeypatch):
    from pathlib import Path

    import pytest

    class FakeResp:
        content = b"not a rar archive"

        def raise_for_status(self) -> None:
            return None

    class FakeSession:
        def get(self, url, timeout=None):
            return FakeResp()

    monkeypatch.setattr(client, "_impersonated_session", lambda: FakeSession())

    made: list[str] = []
    real_mkdtemp = client.tempfile.mkdtemp

    def tracked_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        made.append(d)
        return d

    monkeypatch.setattr(client.tempfile, "mkdtemp", tracked_mkdtemp)

    with pytest.raises(client.HLTVError):
        client._download_and_extract("http://x/demo.rar", "123")

    assert made and not Path(made[0]).exists()


def test_backfill_repairs_the_wrong_match_date(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db import Base
    from app.domain.models import Demo, User
    from app.hltv import backfill

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    admin = User(email="bf@x.io", hashed_password="x", role="admin")
    session.add(admin)
    session.flush()

    download_day = date(2026, 8, 7)
    played = {"2387412": date(2025, 11, 8), "2396004": date(2026, 7, 24)}
    demos = []
    for did, (match_id, map_id) in enumerate(
        [("2387412", "de_train"), ("2387412", "de_nuke"), ("2396004", "de_cache")], start=1
    ):
        demo = Demo(id=did, owner_id=admin.id, map_id=map_id, visibility="public",
                    hltv_match_id=match_id, match_date=download_day, event="Old Event")
        session.add(demo)
        demos.append(demo)
    session.flush()

    fetched: list[str] = []

    def fake_get(url, **kw):
        match_id = url.rstrip("/x").rsplit("/", 1)[-1]
        fetched.append(match_id)
        return _match_page(played=played[match_id], upcoming=date.today() + timedelta(days=1))

    monkeypatch.setattr(client, "_flaresolverr_get", fake_get)

    cache: dict[str, backfill._MatchMeta] = {}
    for demo in demos:
        assert backfill._backfill_one(session, demo, cache) == "updated"

    assert [d.match_date for d in demos] == [played["2387412"], played["2387412"], played["2396004"]]
    assert {d.event for d in demos} == {"IEM Chengdu 2025"}
    assert fetched == ["2387412", "2396004"]  # 3 demos, 2 matches solved


def test_backfill_keeps_a_good_date_when_the_page_cannot_be_read(monkeypatch):
    # A page we fail to parse must not wipe what we already have.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db import Base
    from app.domain.models import Demo, User
    from app.hltv import backfill

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    admin = User(email="bf2@x.io", hashed_password="x", role="admin")
    session.add(admin)
    session.flush()
    known = date(2025, 11, 8)
    demo = Demo(id=1, owner_id=admin.id, map_id="de_train", visibility="public",
                hltv_match_id="2387412", match_date=known, event="IEM Chengdu 2025")
    session.add(demo)
    session.flush()

    monkeypatch.setattr(client, "_flaresolverr_get", lambda url, **kw: "<html>redesigned</html>")
    assert backfill._backfill_one(session, demo, {}) == "skipped"
    assert demo.match_date == known
    assert demo.event == "IEM Chengdu 2025"
