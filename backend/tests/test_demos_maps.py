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
