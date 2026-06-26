from __future__ import annotations

import io

from app.ml.features import SITES, round_features
from app.ml.model import SitePredictor
from tests.conftest import auth, register_and_login


def _upload(client, token, **data):
    files = {"file": ("m.dem", io.BytesIO(b"x"), "application/octet-stream")}
    return client.post("/demos/upload", files=files, data=data, headers=auth(token))


def _admin(client) -> str:
    # Bootstrapped by conftest env (CS2_BOOTSTRAP_ADMIN_*).
    resp = client.post("/auth/login", data={"username": "admin@cs2.local", "password": "admin"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# --- unit: feature extractor + untrained predictor (order-independent) ---

def test_round_features_use_t_side_only():
    feats = round_features(
        map_id="de_mirage",
        team="X",
        opponent="Y",
        buy_type="full",
        equip_value=20_000,
        utility=[
            {"util_type": "smoke", "region": "A", "round_time_s": 5, "side": "t"},
            {"util_type": "flash", "region": "A", "round_time_s": 40, "side": "t"},
            {"util_type": "smoke", "region": "B", "round_time_s": 5, "side": "ct"},
        ],
    )
    assert SITES == ["A", "B", "Mid", "NoPlant"]
    assert feats["u_smoke"] == 1.0  # the CT smoke is ignored
    assert feats["r_A_smoke"] == 1.0
    assert feats["n_util"] == 2.0
    assert feats["n_opening"] == 1.0  # the 40s flash is not "opening"
    assert feats["map"] == "de_mirage"


def test_round_features_time_window_uses_midpoint():
    feats = round_features(
        map_id="de_mirage",
        team="X",
        opponent="Y",
        buy_type="full",
        equip_value=20_000,
        utility=[
            {"util_type": "smoke", "region": "A", "time_from": 4, "time_to": 10, "side": "t"},
            {"util_type": "flash", "region": "B", "time_from": 30, "time_to": 40, "side": "t"},
        ],
    )
    assert feats["t_min"] == 7.0  # midpoint of 4-10
    assert feats["t_mean"] == 21.0  # (7 + 35) / 2
    assert feats["n_opening"] == 1.0  # only the 4-10 window (mid 7) is "opening"


def test_untrained_predictor_returns_none():
    p = SitePredictor()
    assert p.trained is False
    assert (
        p.model_proba(
            map_id="de_mirage", team="X", opponent=None,
            buy_type="full", equip_value=4000, utility=[],
        )
        is None
    )


# --- API ---

def test_predict_contract(client):
    token = register_and_login(client, "mlpredict@example.com")
    _upload(client, token, map_id="de_mirage", team="NaVi", visibility="private")
    resp = client.post(
        "/scouting/predict",
        json={
            "map_id": "de_mirage",
            "team": "NaVi",
            "buy_type": "full",
            "utility": [{"util_type": "smoke", "region": "A", "round_time_s": 8.0, "side": "t"}],
        },
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [s["site"] for s in body["sites"]] == SITES
    assert abs(sum(s["prob"] for s in body["sites"]) - 1.0) < 1e-6
    assert len(body["baseline"]) == 4
    assert body["source"] in ("model", "baseline")
    assert body["predicted_site"] in SITES


def test_predict_accepts_time_window(client):
    token = register_and_login(client, "mlwindow@example.com")
    _upload(client, token, map_id="de_mirage", team="NaVi", visibility="private")
    resp = client.post(
        "/scouting/predict",
        json={
            "map_id": "de_mirage",
            "team": "NaVi",
            "buy_type": "full",
            "utility": [
                {"util_type": "smoke", "region": "A", "time_from": 4.0, "time_to": 12.0, "side": "t"}
            ],
        },
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["predicted_site"] in SITES


def test_train_requires_admin(client):
    token = register_and_login(client, "mlnotadmin@example.com")
    resp = client.post("/scouting/train", headers=auth(token))
    assert resp.status_code == 403


def test_train_then_predict_uses_model(client):
    admin = _admin(client)
    # Distinct teams/maps so the MLP has several hundred labelled T rounds.
    for mp, team in [
        ("de_mirage", "NaVi"), ("de_inferno", "G2"),
        ("de_ancient", "Vitality"), ("de_nuke", "FaZe"),
    ]:
        _upload(client, admin, map_id=mp, team=team, visibility="public")

    trained = client.post("/scouting/train", headers=auth(admin))
    assert trained.status_code == 200, trained.text
    status = trained.json()
    assert status["n_rounds"] > 0
    assert status["trained"] is True
    assert status["baseline_accuracy"] is not None

    got = client.get("/scouting/model", headers=auth(admin)).json()
    assert got["trained"] is True

    resp = client.post(
        "/scouting/predict",
        json={
            "map_id": "de_mirage",
            "team": "NaVi",
            "buy_type": "full",
            "utility": [
                {"util_type": "smoke", "region": "A", "round_time_s": 6.0, "side": "t"},
                {"util_type": "flash", "region": "A", "round_time_s": 9.0, "side": "t"},
            ],
        },
        headers=auth(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "model"


def test_tendencies_returns_sites_and_heatmap(client):
    token = register_and_login(client, "mltend@example.com")
    _upload(client, token, map_id="de_inferno", team="Spirit", visibility="private")
    resp = client.get(
        "/scouting/tendencies",
        params={"map_id": "de_inferno", "team": "Spirit"},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [s["site"] for s in body["sites"]] == SITES
    assert body["total_rounds"] > 0
    assert isinstance(body["heatmap"], list)
    assert len(body["heatmap"]) > 0
    z = body["heatmap"][0]
    assert z["total"] >= z["smoke"] + z["flash"] + z["molotov"] + z["he"]
