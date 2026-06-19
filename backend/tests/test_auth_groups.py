from __future__ import annotations

import io
from tests.conftest import auth, register_and_login


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_register_login_me(client):
    token = register_and_login(client, "alice@example.com")
    me = client.get("/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["role"] == "user"


def test_login_rejects_bad_password(client):
    register_and_login(client, "bob@example.com")
    resp = client.post("/auth/login", data={"username": "bob@example.com", "password": "nope"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_group_invite_flow_and_demo_visibility(client):
    owner = register_and_login(client, "owner@example.com")
    peer = register_and_login(client, "peer@example.com")
    outsider = register_and_login(client, "outsider@example.com")

    # Owner creates a group and invites the peer.
    group = client.post("/groups", json={"name": "Team Liquid"}, headers=auth(owner)).json()
    inv = client.post(
        f"/groups/{group['id']}/invite",
        json={"email": "peer@example.com"},
        headers=auth(owner),
    )
    assert inv.status_code == 201

    pending = client.get("/invitations", headers=auth(peer)).json()
    assert len(pending) == 1
    inv_id = pending[0]["id"]
    accept = client.post(
        f"/invitations/{inv_id}/respond", params={"accept": True}, headers=auth(peer)
    )
    assert accept.status_code == 204

    groups = client.get("/groups", headers=auth(owner)).json()
    assert groups[0]["member_count"] == 2

    # Owner uploads a PRIVATE demo; group peer sees it, outsider does not.
    files = {"file": ("match.dem", io.BytesIO(b"fake-demo-bytes"), "application/octet-stream")}
    up = client.post(
        "/demos/upload",
        files=files,
        data={"map_id": "de_mirage", "team": "Liquid", "visibility": "private"},
        headers=auth(owner),
    )
    assert up.status_code == 201, up.text
    demo_id = up.json()["demo"]["id"]

    assert any(d["id"] == demo_id for d in client.get("/demos", headers=auth(peer)).json())
    assert all(d["id"] != demo_id for d in client.get("/demos", headers=auth(outsider)).json())
    assert client.get(f"/demos/{demo_id}", headers=auth(outsider)).status_code == 403
