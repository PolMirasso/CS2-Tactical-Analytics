from __future__ import annotations

import io

import numpy as np

from app.ml.deepsets import POOLINGS, DeepSets, _softmax
from app.ml.features import SITES, TIMINGS, TOKEN_DIM, round_context, round_tokens, timing_label
from app.ml.model import HOLDOUT_FRAC, SitePredictor, _reliability
from tests.conftest import auth, register_and_login


def _upload(client, token, content=b"x", **data):
    # distinct bytes ⇒ distinct sha256 ⇒ not deduped (sample rounds come from map/team)
    files = {"file": ("m.dem", io.BytesIO(content), "application/octet-stream")}
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


def _synth_rounds(rng, map_id, team, n):
    """Trainable synthetic rounds: A/B separated by x, NoPlant with only late utility."""
    samples, targets = [], []
    for _ in range(n):
        site = rng.choice(["A", "B", "NoPlant"], p=[0.35, 0.35, 0.30])
        x = {"A": 200.0, "B": 800.0, "NoPlant": 500.0}[site]
        t = 90.0 if site == "NoPlant" else 6.0
        util = [{"util_type": "smoke", "x": x, "y": 500.0, "round_time_s": t, "side": "t"}]
        samples.append({
            "tokens": round_tokens(map_id, util),
            "context": round_context(
                map_id=map_id, team=team, opponent="OPP",
                buy_type="full", equip_value=4000, utility=util,
            ),
        })
        targets.append(site)
    return samples, targets


def test_train_reports_per_map_breakdown():
    rng = np.random.default_rng(1)
    samples, targets = [], []
    for mp, team in [("de_mirage", "NaVi"), ("de_inferno", "G2")]:
        s, tg = _synth_rounds(rng, mp, team, 120)
        samples += s
        targets += tg

    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 2})
    assert p.trained
    assert p.per_map

    assert {r["map_id"] for r in p.per_map} <= {"de_mirage", "de_inferno"}
    for r in p.per_map:
        assert r["n_plant"] <= r["n_rounds"]
        assert 0.0 <= r["accuracy"] <= 1.0
        assert 0.0 <= r["baseline_accuracy"] <= 1.0
        assert r["site_accuracy"] is None or 0.0 <= r["site_accuracy"] <= 1.0
    # the per-map rows partition the single held-out split (20%)
    assert sum(r["n_rounds"] for r in p.per_map) == max(2, round(len(samples) * HOLDOUT_FRAC))


# execution-timing head (rush / default / late given a plant)

def test_timing_label_thresholds():
    assert timing_label(None) is None  # no plant → no timing
    assert timing_label(10.0) == "rush"
    assert timing_label(35.0) == "rush"  # boundary is inclusive
    assert timing_label(50.0) == "default"
    assert timing_label(70.0) == "default"
    assert timing_label(90.0) == "late"


def _synth_timed_rounds(rng, map_id, team, n):
    """Plant rounds whose site is decided by x and whose timing is decided by the
    utility throw time (rush=early, late=late) — the tokens-only heads can recover
    both. NoPlant rounds carry no timing label."""
    samples, targets, timings = [], [], []
    for _ in range(n):
        site = rng.choice(["A", "B", "NoPlant"], p=[0.35, 0.35, 0.30])
        if site == "NoPlant":
            x, t, tim = 500.0, 90.0, None
        else:
            x = 200.0 if site == "A" else 800.0
            tim = rng.choice(TIMINGS)
            t = {"rush": 5.0, "default": 22.0, "late": 42.0}[tim]
        util = [{"util_type": "smoke", "x": x, "y": 500.0, "round_time_s": t, "side": "t"}]
        samples.append({
            "tokens": round_tokens(map_id, util),
            "context": round_context(
                map_id=map_id, team=team, opponent="OPP",
                buy_type="full", equip_value=4000, utility=util,
            ),
        })
        targets.append(site)
        timings.append(tim)
    return samples, targets, timings


def test_timing_head_learns_and_beats_baseline():
    rng = np.random.default_rng(5)
    samples, targets, timings = _synth_timed_rounds(rng, "de_mirage", "NaVi", 400)
    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 1}, timings)
    assert p.trained
    assert p.timing_net is not None
    assert p.timing_classes == TIMINGS  # all three present, canonical order
    assert p.timing_accuracy is not None and p.timing_accuracy >= 0.8
    assert p.timing_accuracy > (p.timing_baseline_accuracy or 0.0)
    assert "timing" in p.params and "timing_T" in p.params


def test_timing_proba_responds_to_throw_time():
    rng = np.random.default_rng(6)
    samples, targets, timings = _synth_timed_rounds(rng, "de_mirage", "NaVi", 400)
    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 1}, timings)

    def timing_at(t: float) -> dict[str, float]:
        return p.timing_proba(
            map_id="de_mirage",
            utility=[{
                "util_type": "smoke", "x": 200.0, "y": 500.0,
                "w": 40.0, "h": 40.0, "time_from": t, "time_to": t, "side": "t",
            }],
        )

    early, late = timing_at(5.0), timing_at(42.0)
    assert early is not None and late is not None
    assert abs(sum(early.values()) - 1.0) < 1e-6
    assert set(early) == set(TIMINGS)
    assert early["rush"] > early["late"]  # early utility ⇒ rush
    assert late["late"] > late["rush"]  # late utility ⇒ late


def test_timing_head_off_without_labels():
    # No timing labels (old un-reparsed data) ⇒ the timing head stays off, the
    # site model still trains, and timing_proba returns None.
    rng = np.random.default_rng(7)
    samples, targets = _synth_rounds(rng, "de_mirage", "NaVi", 200)
    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 1})
    assert p.trained
    assert p.timing_net is None
    assert p.timing_accuracy is None
    assert p.timing_proba(map_id="de_mirage", utility=[]) is None


# 80/20 holdout evaluation + prediction driven by the selected (drawn) utility

def test_train_holds_out_20_percent_for_evaluation():
    """Fit on 80%, keep the other 20% untouched: per_map rows cover exactly the
    held-out split and n_plant never exceeds n_rounds inside it."""
    rng = np.random.default_rng(2)
    samples, targets = _synth_rounds(rng, "de_mirage", "NaVi", 300)
    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 1})
    assert p.trained
    n_val = sum(r["n_rounds"] for r in p.per_map)
    assert n_val == max(2, round(len(samples) * HOLDOUT_FRAC))  # ~20% held out
    assert round(len(samples) * HOLDOUT_FRAC) == 60  # 20% of 300


def test_holdout_evaluation_shows_model_is_correct():
    """The honest test: train on 80%, score on the held-out 20%. With the site
    fully decided by the utility position, the model recovers it on unseen rounds
    far better than the historical base-rate baseline."""
    rng = np.random.default_rng(3)
    samples, targets = [], []
    for mp, team in [("de_mirage", "NaVi"), ("de_inferno", "G2")]:
        s, tg = _synth_rounds(rng, mp, team, 200)
        samples += s
        targets += tg

    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 2})
    assert p.trained
    # A-vs-B given a plant is the real job and position decides it here → near-perfect
    assert p.site_accuracy is not None and p.site_accuracy >= 0.9
    # 3-class accuracy on the held-out rows clears the base rate on those same rows
    assert p.accuracy is not None and p.baseline_accuracy is not None
    assert p.accuracy > p.baseline_accuracy


def test_prediction_follows_selected_utility_box():
    """'El recuadro manda': after training, the SAME drawn box predicts A when
    placed on the A side and B when placed on the B side — the selected utility's
    position, not the context, drives the call."""
    rng = np.random.default_rng(4)
    samples, targets = _synth_rounds(rng, "de_mirage", "NaVi", 300)
    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 1})
    assert p.trained

    def predict_box(x: float) -> dict[str, float] | None:
        return p.model_proba(
            map_id="de_mirage", team="NaVi", opponent="OPP",
            buy_type="full", equip_value=4000,
            utility=[{
                "util_type": "smoke", "x": x, "y": 500.0,
                "w": 60.0, "h": 60.0, "time_from": 4.0, "time_to": 8.0, "side": "t",
            }],
        )

    a_box = predict_box(200.0)  # box drawn on the A side
    b_box = predict_box(800.0)  # box drawn on the B side
    assert a_box is not None and b_box is not None
    assert a_box["A"] > a_box["B"]  # box on A ⇒ A wins
    assert b_box["B"] > b_box["A"]  # box on B ⇒ B wins
    # sliding the box A→B trades probability mass the expected way
    assert b_box["B"] > a_box["B"]
    assert a_box["A"] > b_box["A"]


# API


def test_predict_accepts_selected_utility_box(client):
    # drawn-box utility (x/y + w/h) — the scouting "select utility" input — plumbs
    # through /scouting/predict and returns a valid, normalised distribution
    token = register_and_login(client, "mlbox@example.com")
    _upload(client, token, map_id="de_mirage", team="NaVi", visibility="private")
    resp = client.post(
        "/scouting/predict",
        json={
            "map_id": "de_mirage",
            "team": "NaVi",
            "buy_type": "full",
            "utility": [{
                "util_type": "smoke", "x": 200.0, "y": 500.0,
                "w": 60.0, "h": 60.0, "time_from": 4.0, "time_to": 8.0, "side": "t",
            }],
        },
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [s["site"] for s in body["sites"]] == SITES
    assert abs(sum(s["prob"] for s in body["sites"]) - 1.0) < 1e-6
    assert body["predicted_site"] in SITES


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
    # distinct maps/teams (distinct bytes) ⇒ multi-map dataset
    for mp, team in [
        ("de_mirage", "NaVi"), ("de_inferno", "G2"),
        ("de_ancient", "Vitality"), ("de_nuke", "FaZe"),
    ]:
        _upload(client, admin, content=f"demo-{mp}".encode(), map_id=mp, team=team, visibility="public")

    trained = client.post("/scouting/train", headers=auth(admin))
    assert trained.status_code == 200, trained.text
    status = trained.json()
    assert status["n_rounds"] > 0
    assert status["trained"] is True
    assert status["baseline_accuracy"] is not None

    got = client.get("/scouting/model", headers=auth(admin)).json()
    assert got["trained"] is True

    # Per-map breakdown flows through the ModelStatusOut response_model (both routes)
    uploaded = {"de_mirage", "de_inferno", "de_ancient", "de_nuke"}
    for payload in (status, got):
        per_map = payload["per_map"]
        assert isinstance(per_map, list)
        assert len(per_map) >= 2  # several maps land in the held-out split
        assert {r["map_id"] for r in per_map} <= uploaded
        for r in per_map:
            assert 0 <= r["n_plant"] <= r["n_rounds"]
            assert 0.0 <= r["accuracy"] <= 1.0
            assert r["site_accuracy"] is None or 0.0 <= r["site_accuracy"] <= 1.0

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
    body = resp.json()
    assert body["source"] == "model"
    # Timing head trained from the sample plant-times and plumbs through predict
    assert status["timing_accuracy"] is not None
    assert [tp["timing"] for tp in body["timing"]] == TIMINGS
    assert abs(sum(tp["prob"] for tp in body["timing"]) - 1.0) < 1e-6
    assert body["predicted_timing"] in TIMINGS


def test_evaluate_requires_admin(client):
    token = register_and_login(client, "mlevalnotadmin@example.com")
    resp = client.post("/scouting/evaluate", headers=auth(token))
    assert resp.status_code == 403


def test_evaluate_reports_per_map_ok_without_persisting(client):
    admin = _admin(client)
    for mp, team in [
        ("de_mirage", "NaVi"), ("de_inferno", "G2"),
        ("de_ancient", "Vitality"), ("de_nuke", "FaZe"),
    ]:
        _upload(client, admin, content=f"eval-{mp}".encode(), map_id=mp, team=team, visibility="public")

    before = client.get("/scouting/model", headers=auth(admin)).json()
    resp = client.post("/scouting/evaluate", headers=auth(admin))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["trained"] is True
    assert body["per_map"]
    for r in body["per_map"]:
        assert 0 <= r["n_plant"] <= r["n_rounds"]
        assert r["accuracy"] is None or 0.0 <= r["accuracy"] <= 1.0  # % OK per map
    # "test all maps" evaluates only — it must never persist or swap the deployed model
    after = client.get("/scouting/model", headers=auth(admin)).json()
    assert after == before


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
