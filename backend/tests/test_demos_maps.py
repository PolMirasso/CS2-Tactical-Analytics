from __future__ import annotations

import io
from tests.conftest import auth, register_and_login


def _upload(client, token, **data):
    files = {"file": ("m.dem", io.BytesIO(b"x"), "application/octet-stream")}
    return client.post("/demos/upload", files=files, data=data, headers=auth(token))


def test_upload_parses_rounds_and_utility(client):
    token = register_and_login(client, "analyst@example.com")
    resp = _upload(client, token, map_id="de_mirage", team="Vitality", visibility="private")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["demo"]["status"] == "parsed"
    assert body["rounds"] == 24
    assert body["utility_events"] > 0


def test_demo_analysis_returns_rounds_and_utility(client):
    token = register_and_login(client, "analysis@example.com")
    up = _upload(client, token, map_id="de_mirage", team="Vitality", visibility="private")
    demo_id = up.json()["demo"]["id"]
    resp = client.get(f"/demos/{demo_id}/analysis", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["demo"]["id"] == demo_id
    assert len(body["rounds"]) == 24
    assert any(len(r["utility"]) > 0 for r in body["rounds"])
    r0 = body["rounds"][0]
    assert {"round_number", "buy_type", "target_site", "utility"} <= set(r0)


def test_reparse_is_idempotent(client):
    token = register_and_login(client, "reparser@example.com")
    up = _upload(client, token, map_id="de_inferno", team="G2", visibility="private")
    demo_id = up.json()["demo"]["id"]
    again = client.post(f"/demos/{demo_id}/parse", headers=auth(token))
    assert again.status_code == 200
    assert again.json()["rounds"] == up.json()["rounds"]


def test_upload_dedup_same_file(client):
    token = register_and_login(client, "dedup@example.com")
    first = _upload(client, token, map_id="de_mirage", visibility="private")
    second = _upload(client, token, map_id="de_mirage", visibility="private")
    assert first.json()["demo"]["id"] == second.json()["demo"]["id"]
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["rounds"] == first.json()["rounds"]
    assert second.json()["utility_events"] == first.json()["utility_events"]


def test_non_dem_rejected(client):
    token = register_and_login(client, "nondem@example.com")
    files = {"file": ("notes.txt", io.BytesIO(b"x"), "text/plain")}
    resp = client.post("/demos/upload", files=files, data={}, headers=auth(token))
    assert resp.status_code == 400


def test_public_upload_requires_admin(client):
    token = register_and_login(client, "wannabe@example.com")
    resp = _upload(client, token, map_id="de_mirage", visibility="public")
    assert resp.status_code == 403


def test_delete_demo(client):
    token = register_and_login(client, "deleter@example.com")
    up = _upload(client, token, map_id="de_inferno", visibility="private")
    demo_id = up.json()["demo"]["id"]
    assert client.delete(f"/demos/{demo_id}", headers=auth(token)).status_code == 204
    assert client.get(f"/demos/{demo_id}", headers=auth(token)).status_code == 404


def test_delete_demo_removes_kills_and_player_stats(client):
    from sqlalchemy import func, select
    from app.db import session_scope
    from app.domain.models import Kill, PlayerStat, Round, UtilityEvent

    token = register_and_login(client, "deepdelete@example.com")
    up = _upload(client, token, map_id="de_mirage", team="NAVI", visibility="private")
    demo_id = up.json()["demo"]["id"]

    def counts() -> tuple[int, ...]:
        with session_scope() as session:
            return tuple(
                session.scalar(
                    select(func.count()).select_from(t).where(t.demo_id == demo_id)
                )
                for t in (Round, UtilityEvent, Kill, PlayerStat)
            )

    assert all(n > 0 for n in counts())
    assert client.delete(f"/demos/{demo_id}", headers=auth(token)).status_code == 204
    assert counts() == (0, 0, 0, 0)


def test_reparse_all_keeps_uploaded_demo_teams(client):
    from app.demos import reparse

    token = register_and_login(client, "reparseteams@example.com")
    up = _upload(
        client, token, map_id="de_train", team="MOUZ", opponent="ENCE",
        visibility="private",
    )
    demo_id = up.json()["demo"]["id"]

    reparse._run("de_train")

    body = client.get(f"/demos/{demo_id}", headers=auth(token)).json()
    assert body["status"] == "parsed"
    assert (body["team"], body["opponent"]) == ("MOUZ", "ENCE")

    # Drop the de_train rounds so later tests keep their expected map set.
    assert client.delete(f"/demos/{demo_id}", headers=auth(token)).status_code == 204


def test_replay_meta_lists_rounds(client):
    token = register_and_login(client, "replaymeta@example.com")
    up = _upload(client, token, map_id="de_mirage", team="Vitality", visibility="private")
    demo_id = up.json()["demo"]["id"]
    resp = client.get(f"/demos/{demo_id}/replay", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["demo_id"] == demo_id
    assert body["map_id"] == "de_mirage"
    assert body["sample_hz"] > 0
    assert len(body["rounds"]) == 24
    r0 = body["rounds"][0]
    assert r0["n_players"] == 10
    assert r0["n_frames"] > 0
    # Radar background is advertised on the replay meta itself.
    assert "has_radar" in body and "calibration" in body
    if body["calibration"] is not None:
        assert {"pos_x", "pos_y", "scale"} <= set(body["calibration"])


def test_replay_round_returns_frames_and_lines(client):
    token = register_and_login(client, "replayround@example.com")
    up = _upload(client, token, map_id="de_mirage", team="Vitality", visibility="private")
    demo_id = up.json()["demo"]["id"]
    resp = client.get(f"/demos/{demo_id}/replay/1", headers=auth(token))
    assert resp.status_code == 200, resp.text
    rd = resp.json()
    assert rd["round_number"] == 1
    assert len(rd["players"]) == 10
    assert len(rd["frames"]) > 0
    # Each frame carries one [x, y, yaw, hp, z] per player, aligned to the roster.
    assert len(rd["frames"][0]["pos"]) == len(rd["players"])
    assert len(rd["frames"][0]["pos"][0]) == 5
    # Utility carries a throw→land line.
    if rd["utility"]:
        u = rd["utility"][0]
        assert {"type", "t", "from", "to"} <= set(u)
        assert len(u["from"]) == 2 and len(u["to"]) == 2


def test_replay_missing_round_404(client):
    token = register_and_login(client, "replay404@example.com")
    up = _upload(client, token, map_id="de_mirage", visibility="private")
    demo_id = up.json()["demo"]["id"]
    assert client.get(f"/demos/{demo_id}/replay/999", headers=auth(token)).status_code == 404


def test_replay_gone_after_delete(client):
    token = register_and_login(client, "replaydel@example.com")
    up = _upload(client, token, map_id="de_inferno", visibility="private")
    demo_id = up.json()["demo"]["id"]
    assert client.get(f"/demos/{demo_id}/replay", headers=auth(token)).status_code == 200
    client.delete(f"/demos/{demo_id}", headers=auth(token))
    assert client.get(f"/demos/{demo_id}/replay", headers=auth(token)).status_code == 404


def test_maps_radar_and_calibration(client):
    token = register_and_login(client, "radar@example.com")
    maps = client.get("/maps", headers=auth(token)).json()
    mirage = next(m for m in maps if m["id"] == "de_mirage")
    assert "has_radar" in mirage and "calibration" in mirage
    if mirage["calibration"] is not None:
        assert {"pos_x", "pos_y", "scale"} <= set(mirage["calibration"])
    # Radar image endpoint is consistent with the has_radar flag.
    img = client.get("/maps/de_mirage/radar.png", headers=auth(token))
    if mirage["has_radar"]:
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/png"
    else:
        assert img.status_code == 404


def test_maps_endpoint(client):
    token = register_and_login(client, "maps@example.com")
    maps = client.get("/maps", headers=auth(token)).json()
    ids = {m["id"] for m in maps}
    assert {"de_mirage", "de_inferno"} <= ids
    mirage = next(m for m in maps if m["id"] == "de_mirage")
    assert len(mirage["zones"]) > 0
    zone = mirage["zones"][0]
    assert {"id", "name", "region", "centroid"} <= set(zone)
    assert zone["region"] in {"A", "B", "Mid"}
    assert len(zone["centroid"]) == 2


def test_maps_endpoint_is_public_route_but_needs_auth(client):
    resp = client.get("/maps")
    assert resp.status_code == 200

def test_analysis_includes_players_and_winner(client):
    token = register_and_login(client, "scout@example.com")
    up = _upload(client, token, map_id="de_mirage", team="Vitality", visibility="private")
    demo_id = up.json()["demo"]["id"]
    body = client.get(f"/demos/{demo_id}/analysis", headers=auth(token)).json()
    players = body["players"]
    assert len(players) == 10
    assert {"name", "kills", "deaths", "assists", "headshots", "adr", "team"} <= set(players[0])
    teams = [p["team"] for p in players]
    assert len(set(teams)) == 2
    by_team: dict[str, list[int]] = {}
    for p in players:
        by_team.setdefault(p["team"], []).append(p["kills"])
    for kills in by_team.values():
        assert kills == sorted(kills, reverse=True)
    assert all(r["winner"] in ("t", "ct") for r in body["rounds"])


def test_apply_canonical_teams_tags_ids_and_drops_names(client):
    # Each clan is mapped to its HLTV id on the demo and its rounds; no names stored.
    from sqlalchemy import select
    from app.db import session_scope
    from app.demos import service
    from app.domain.enums import DemoSource
    from app.domain.models import Demo, Round, User

    with session_scope() as session:
        owner = session.scalar(select(User))
        demo = Demo(
            owner_id=owner.id, source=str(DemoSource.HLTV), map_id="de_mirage",
            team="vitality-tag", opponent="faze-tag",
        )
        session.add(demo)
        session.flush()
        # T-side clan alternates across the halves -> both clans appear.
        session.add(Round(demo_id=demo.id, round_number=1, map_id="de_mirage",
                          team="vitality-tag", opponent="faze-tag", buy_type="pistol",
                          target_site="A"))
        session.add(Round(demo_id=demo.id, round_number=13, map_id="de_mirage",
                          team="faze-tag", opponent="vitality-tag", buy_type="full",
                          target_site="B"))
        session.flush()

        service.upsert_team(session, "9565", "Team Vitality")
        service.upsert_team(session, "6667", "FaZe")
        service.apply_canonical_teams(
            session, demo, team_hltv_id="9565", opponent_hltv_id="6667"
        )

        assert (demo.team, demo.opponent) == (None, None)
        assert (demo.team_hltv_id, demo.opponent_hltv_id) == ("9565", "6667")
        assert service.resolve_team_names(session, {"9565", "6667"}) == {
            "9565": "Team Vitality", "6667": "FaZe",
        }
        rounds = list(session.scalars(
            select(Round).where(Round.demo_id == demo.id)
        ))
        for r in rounds:
            assert r.team_hltv_id in ("9565", "6667")
            assert r.opponent_hltv_id in ("9565", "6667")
        r13 = next(r for r in rounds if r.round_number == 13)
        # Round 13: faze-tag executes vs vitality-tag.
        assert (r13.team_hltv_id, r13.opponent_hltv_id) == ("6667", "9565")


def test_demo_list_pagination_and_filter(client):
    token = register_and_login(client, "pager@example.com")
    _upload(client, token, map_id="de_nuke", team="Spirit", visibility="private")
    listing = client.get("/demos", params={"map_id": "de_nuke", "limit": 1}, headers=auth(token)).json()
    assert "items" in listing and "total" in listing
    assert len(listing["items"]) <= 1
    assert all(d["map_id"] == "de_nuke" for d in listing["items"])
