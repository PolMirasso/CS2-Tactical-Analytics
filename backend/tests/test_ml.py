from __future__ import annotations

import io

import numpy as np

from app.ml.deepsets import POOLINGS, DeepSets, _softmax
from app.ml.features import SITES, TOKEN_DIM, round_context, round_tokens
from app.ml.model import SitePredictor, _reliability
from tests.conftest import auth, register_and_login


def _upload(client, token, **data):
    files = {"file": ("m.dem", io.BytesIO(b"x"), "application/octet-stream")}
    return client.post("/demos/upload", files=files, data=data, headers=auth(token))


def _admin(client) -> str:
    # Bootstrapped by conftest env (CS2_BOOTSTRAP_ADMIN_*).
    resp = client.post("/auth/login", data={"username": "admin@cs2.local", "password": "admin"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# unit: token/context builders + untrained predictor (order-independent)

def test_round_tokens_use_t_side_only_and_position():
    tokens = round_tokens(
        "de_mirage",
        [
            {"util_type": "smoke", "x": 100.0, "y": 200.0, "round_time_s": 5, "side": "t"},
            {"util_type": "flash", "x": 300.0, "y": 400.0, "round_time_s": 40, "side": "t"},
            {"util_type": "smoke", "x": 500.0, "y": 600.0, "round_time_s": 5, "side": "ct"},
        ],
    )
    assert SITES == ["A", "B", "NoPlant"]
    assert len(tokens) == 2  # the CT smoke is ignored
    assert all(len(tk) == TOKEN_DIM for tk in tokens)
    assert tokens[0][:4] == [1.0, 0.0, 0.0, 0.0]  # smoke one-hot
    assert tokens[1][:4] == [0.0, 1.0, 0.0, 0.0]  # flash one-hot
    assert tokens[0][4] == 100.0 / 1024.0  # x normalised to 1024-space
    assert tokens[0][5] == 200.0 / 1024.0


def test_round_tokens_fall_back_to_region_centroid():
    # x/y: the position is resolved from the region centroid, still in [0, 1]
    tokens = round_tokens(
        "de_mirage",
        [{"util_type": "smoke", "region": "A", "round_time_s": 5, "side": "t"}],
    )
    assert len(tokens) == 1
    assert 0.0 <= tokens[0][4] <= 1.0 and 0.0 <= tokens[0][5] <= 1.0


def test_round_tokens_z_level_separates_nuke_upper_lower():
    # nuke a upper b lowwer 
    upper = round_tokens(
        "de_nuke",
        [{"util_type": "smoke", "x": 500.0, "y": 500.0, "round_time_s": 5, "side": "t", "z": 0.0}],
    )
    lower = round_tokens(
        "de_nuke",
        [{"util_type": "smoke", "x": 500.0, "y": 500.0, "round_time_s": 5, "side": "t", "z": -600.0}],
    )
    unknown = round_tokens(
        "de_nuke",
        [{"util_type": "smoke", "x": 500.0, "y": 500.0, "round_time_s": 5, "side": "t"}],
    )
    single = round_tokens(
        "de_mirage",
        [{"util_type": "smoke", "x": 500.0, "y": 500.0, "round_time_s": 5, "side": "t", "z": -600.0}],
    )
    assert upper[0][7] == 0.0
    assert lower[0][7] == 1.0
    assert unknown[0][7] == 0.5
    assert single[0][7] == 0.5


def test_round_context_t_side_and_timing():
    ctx = round_context(
        map_id="de_mirage",
        team="X",
        opponent="Y",
        buy_type="full",
        equip_value=20_000,
        utility=[
            {"util_type": "smoke", "region": "A", "time_from": 4, "time_to": 10, "side": "t"},
            {"util_type": "flash", "region": "B", "time_from": 30, "time_to": 40, "side": "t"},
            {"util_type": "smoke", "region": "B", "round_time_s": 5, "side": "ct"},
        ],
    )
    assert ctx["map"] == "de_mirage"
    assert ctx["u_smoke"] == 1.0  # the CT smoke is ignored
    assert ctx["u_flash"] == 1.0
    assert ctx["n_util"] == 2.0
    assert ctx["n_opening"] == 1.0  # only the 4-10 window (mid 7) is "opening"
    assert ctx["t_min"] == 7.0 / 115.0  # midpoint of 4-10, normalised by round time
    assert ctx["t_mean"] == 21.0 / 115.0  # ((7 + 35) / 2) / 115


# deepSets pooling (fwd/bwd) + temperature calibration
def _finite_diff_grad_ok(pooling: str) -> None:
    """Every param's analytic grad matches central finite differences of the loss."""
    rng = np.random.default_rng(1)
    net = DeepSets._init(5, 4, 3, h_phi=7, d_embed=6, h_rho=8, pooling=pooling, seed=1)
    tokens = rng.standard_normal((4, 5))
    ctx = rng.standard_normal(4)
    y = 2
    _, grads = net._backward_one(tokens, ctx, y)

    def loss() -> float:
        return float(-np.log(_softmax(net.predict_logits(tokens, ctx))[y] + 1e-12))

    eps = 1e-6
    for k, p in net.params.items():
        flat, g = p.ravel(), grads[k].ravel()
        for j in range(flat.size):
            orig = flat[j]
            flat[j] = orig + eps
            lp = loss()
            flat[j] = orig - eps
            lm = loss()
            flat[j] = orig
            num = (lp - lm) / (2 * eps)
            assert abs(num - g[j]) < 1e-4, (pooling, k, j, num, g[j])


def test_all_poolings_backprop_matches_finite_differences():
    for pooling in POOLINGS:
        _finite_diff_grad_ok(pooling)


def test_sum_pool_keeps_cardinality_and_attention_is_normalised():
    z2 = np.ones((3, 6))
    pooled_sum, _ = DeepSets._init(5, 4, 2, d_embed=6, pooling="sum")._pool(z2)
    assert np.allclose(pooled_sum, 3.0)

    net = DeepSets._init(5, 4, 2, d_embed=6, pooling="attention", seed=0)
    z2 = np.random.default_rng(0).standard_normal((5, 6))
    net.params["w_att"] = z2[0].copy()
    pooled, (_, _, (_, att)) = net._pool(z2)
    assert abs(att.sum() - 1.0) < 1e-9 
    assert not np.allclose(pooled, z2.mean(axis=0)) 


def test_fit_temperature_softens_overconfident_logits():
    rng = np.random.default_rng(0)
    n = 200
    y = rng.integers(0, 2, n)
    logits = np.zeros((n, 2))
    for i in range(n):
        cls = y[i] if rng.random() < 0.7 else 1 - y[i]  
        logits[i, cls] = 6.0 
    t = DeepSets.fit_temperature(logits, y)
    assert t > 1.0 
    assert DeepSets._nll(logits, y, t) < DeepSets._nll(logits, y, 1.0)


def test_temperature_preserves_binary_argmax():
    net = DeepSets._init(5, 3, 2, seed=0)
    rng = np.random.default_rng(0)
    tokens, ctx = rng.standard_normal((3, 5)), rng.standard_normal(3)
    before = int(np.argmax(net.predict_proba(tokens, ctx)))
    net.temperature = 4.2
    assert int(np.argmax(net.predict_proba(tokens, ctx))) == before


def test_reliability_ece():
    ece, bins = _reliability([0.9] * 10, [1] * 9 + [0])
    assert abs(ece) < 1e-9
    assert len(bins) == 1 and bins[0]["count"] == 10

    ece2, _ = _reliability([0.99] * 10, [1] + [0] * 9)
    assert abs(ece2 - 0.89) < 1e-9


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


# API

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
    assert len(body["baseline"]) == 3
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
