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
    # All four canonical sites are always present (zero-padded) and ordered.
    assert [s["site"] for s in sites] == ["A", "B", "Mid", "NoPlant"]
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


def test_analytics_teams_lists_executing_team(client):
    token = register_and_login(client, "teamslist@example.com")
    _upload(client, token, map_id="de_ancient", team="Spirit", visibility="private")
    resp = client.get(
        "/analytics/teams", params={"map_id": "de_ancient"}, headers=auth(token)
    )
    assert resp.status_code == 200
    assert "Spirit" in resp.json()


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
