from __future__ import annotations

import io

from tests.conftest import auth, register_and_login


def _upload(client, token, **data):
    files = {"file": ("m.dem", io.BytesIO(b"x"), "application/octet-stream")}
    return client.post("/demos/upload", files=files, data=data, headers=auth(token))


def test_site_distribution_aggregates_rounds(client):
    token = register_and_login(client, "siteagg@example.com")
    _upload(client, token, map_id="de_mirage", team="Vitality", visibility="private")

    resp = client.get(
        "/analytics/site-distribution",
        params={"map_id": "de_mirage", "team": "Vitality"},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["map_id"] == "de_mirage"
    assert body["total_rounds"] > 0
    assert body["total_demos"] >= 1

    sites = body["sites"]
    # The canonical plant sites are always present (zero-padded) and ordered.
    assert [s["site"] for s in sites] == ["A", "B", "NoPlant"]
    assert sum(s["rounds"] for s in sites) == body["total_rounds"]
    assert abs(sum(s["pct"] for s in sites) - 1.0) < 1e-6
    for s in sites:
        assert 0.0 <= s["win_rate"] <= 1.0
        assert s["wins"] <= s["rounds"]
    assert 0.0 <= body["overall_win_rate"] <= 1.0


def test_site_distribution_buy_filter_subsets_rounds(client):
    token = register_and_login(client, "buyfilter@example.com")
    _upload(client, token, map_id="de_inferno", team="G2", visibility="private")

    base = "/analytics/site-distribution"
    full = client.get(base, params={"map_id": "de_inferno"}, headers=auth(token)).json()
    pistols = client.get(
        base, params={"map_id": "de_inferno", "buy_type": "pistol"}, headers=auth(token)
    ).json()
    assert 0 < pistols["total_rounds"] <= full["total_rounds"]


def test_site_distribution_aggregates_multiple_teams(client):
    token = register_and_login(client, "multiteam@example.com")

    def upload(content, team):
        files = {"file": ("m.dem", io.BytesIO(content), "application/octet-stream")}
        return client.post(
            "/demos/upload",
            files=files,
            data={"map_id": "de_mirage", "team": team, "visibility": "private"},
            headers=auth(token),
        )

    # Distinct bytes so the content-hash dedup keeps both demos.
    upload(b"alpha-demo", "MTeamAlpha")
    upload(b"bravo-demo", "MTeamBravo")

    base = "/analytics/site-distribution"
    a = client.get(base, params={"map_id": "de_mirage", "team": "MTeamAlpha"}, headers=auth(token)).json()
    b = client.get(base, params={"map_id": "de_mirage", "team": "MTeamBravo"}, headers=auth(token)).json()
    both = client.get(
        base, params={"map_id": "de_mirage", "team": ["MTeamAlpha", "MTeamBravo"]}, headers=auth(token)
    ).json()

    assert a["total_rounds"] > 0 and b["total_rounds"] > 0
    # Selecting both teams pools their rounds into one distribution.
    assert both["total_rounds"] == a["total_rounds"] + b["total_rounds"]
    assert a["total_rounds"] < both["total_rounds"]
    # The single-team echo is dropped once several teams are selected.
    assert both["team"] is None


def test_analytics_teams_lists_executing_team(client):
    token = register_and_login(client, "teamslist@example.com")
    _upload(client, token, map_id="de_ancient", team="Spirit", visibility="private")
    resp = client.get(
        "/analytics/teams", params={"map_id": "de_ancient"}, headers=auth(token)
    )
    assert resp.status_code == 200
    # id-less (uploaded) demos surface as {id: raw-clan, name: raw-clan}.
    assert "Spirit" in [t["name"] for t in resp.json()]


def test_roster_endpoint_stable_lineup(client):
    token = register_and_login(client, "roster1@example.com")
    _upload(client, token, map_id="de_mirage", team="Falcons", visibility="private")
    resp = client.get(
        "/analytics/roster",
        params={"map_id": "de_mirage", "team": "Falcons"},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # A single demo cannot change line-up, so no warning must fire.
    assert body["has_changes"] is False
    assert body["n_demos"] >= 1


def test_team_rosters_flags_lineup_change():
    """The swap is dated by hltv_match_id (not demo_id) so in/out isn't reversed.

    Mirrors the real HLTV shape: a batch shares the same download match_date and
    is ingested newest-first (so demo_id runs opposite to chronology). Only the
    monotonic hltv_match_id recovers the true order.
    """
    from datetime import date

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.analytics import aggregate
    from app.db import Base
    from app.domain.models import Demo, PlayerStat, Round, User

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    admin = User(email="ru@x.io", hashed_password="x", role="admin")
    session.add(admin)
    session.flush()

    same_day = date(2026, 7, 15)

    def make(did, match_id, roster):
        session.add(
            Demo(id=did, owner_id=admin.id, map_id="de_mirage", visibility="public",
                 team_hltv_id="100", match_date=same_day, hltv_match_id=match_id)
        )
        session.add(
            Round(demo_id=did, round_number=1, map_id="de_mirage", team="TeamA",
                  team_hltv_id="100", buy_type="full", equip_value=4000,
                  target_site="A", winner="t")
        )
        for sid, name in roster:
            session.add(PlayerStat(demo_id=did, steamid=sid, name=name, team="TeamA"))
        session.flush()

    old = [("1", "p1"), ("2", "p2"), ("3", "p3"), ("4", "p4"), ("9", "old")]
    new = [("1", "p1"), ("2", "p2"), ("3", "p3"), ("4", "p4"), ("10", "new")]
    # demo_id runs opposite to chronology; hltv_match_id is the true order.
    make(38, "2395698", new)  # newest match -> current roster
    make(39, "2395210", old)
    make(40, "2395201", old)
    make(41, "2395133", old)  # oldest match -> former roster
    make(42, "2395999", [("1", "p1"), ("2", "p2"), ("3", "p3"), ("10", "new")])  # newest but incomplete: no flag

    out = aggregate.team_rosters(session, admin, map_id="de_mirage", team="100")
    assert out.has_changes is True
    assert out.core == ["p1", "p2", "p3", "p4"]
    # Chronological, oldest first, driven by hltv_match_id.
    assert [e.demo_id for e in out.entries] == [41, 40, 39, 38, 42]
    swap = next(e for e in out.entries if e.added or e.removed)
    assert swap.demo_id == 38  # the change lands on the most recent full demo
    assert swap.added == ["new"] and swap.removed == ["old"]
    gap = next(e for e in out.entries if e.demo_id == 42)
    assert gap.complete is False
    assert gap.added == [] and gap.removed == []


def test_team_rosters_ignores_rename_same_steamid():
    """A player who changes nick (same steamid) must not read as a roster change."""
    from datetime import date

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.analytics import aggregate
    from app.db import Base
    from app.domain.models import Demo, PlayerStat, Round, User

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    admin = User(email="rn@x.io", hashed_password="x", role="admin")
    session.add(admin)
    session.flush()

    def make(did, match_id, roster):
        session.add(
            Demo(id=did, owner_id=admin.id, map_id="de_mirage", visibility="public",
                 team_hltv_id="100", match_date=date(2026, 7, 15), hltv_match_id=match_id)
        )
        session.add(
            Round(demo_id=did, round_number=1, map_id="de_mirage", team="TeamA",
                  team_hltv_id="100", buy_type="full", equip_value=4000,
                  target_site="A", winner="t")
        )
        for sid, name in roster:
            session.add(PlayerStat(demo_id=did, steamid=sid, name=name, team="TeamA"))
        session.flush()

    # Same five steamids in both demos; player "5" renamed guardian -> guardiaN.
    make(1, "300", [("1", "p1"), ("2", "p2"), ("3", "p3"), ("4", "p4"), ("5", "guardian")])
    make(2, "301", [("1", "p1"), ("2", "p2"), ("3", "p3"), ("4", "p4"), ("5", "guardiaN")])

    out = aggregate.team_rosters(session, admin, map_id="de_mirage", team="100")
    assert out.has_changes is False
    assert all(not e.added and not e.removed for e in out.entries)
    # Core is the five stable steamids, labelled with the most recent nick.
    assert "guardiaN" in out.core and "guardian" not in out.core


def test_site_distribution_respects_visibility(client):
    owner = register_and_login(client, "agowner@example.com")
    _upload(client, owner, map_id="de_nuke", team="FaZe", visibility="private")

    other = register_and_login(client, "agother@example.com")
    body = client.get(
        "/analytics/site-distribution",
        params={"map_id": "de_nuke", "team": "FaZe"},
        headers=auth(other),
    ).json()
    # Another user's private demo must not leak into the aggregate.
    assert body["total_rounds"] == 0
    assert body["total_demos"] == 0
