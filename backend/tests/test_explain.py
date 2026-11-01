from __future__ import annotations

from itertools import combinations

import numpy as np
import pytest

from app.ml.deepsets import POOLINGS, DeepSets
from app.ml.explain import (
    CONTEXT_GROUPS,
    exact_shapley,
    gate_value,
    masked_logits,
    sampled_shapley,
    shapley,
    site_value,
    token_zone,
)
from app.ml.features import round_context, round_tokens
from app.ml.model import SitePredictor, _to_array


@pytest.mark.parametrize("pooling", POOLINGS)
def test_masked_logits_match_the_net_on_every_subset(pooling):
    rng = np.random.default_rng(0)
    net = DeepSets._init(5, 3, 2, h_phi=7, d_embed=6, h_rho=8, pooling=pooling, seed=2)
    net.params["w_att"] = rng.standard_normal(6) if pooling == "attention" else None
    if pooling != "attention":
        net.params.pop("w_att")
    tokens = rng.standard_normal((4, 5))
    ctx = rng.standard_normal(3)
    masks = np.array([[(m >> i) & 1 for i in range(4)] for m in range(16)], dtype=bool)
    got = masked_logits(net, tokens, masks, ctx)
    for m, row in zip(masks, got, strict=True):
        np.testing.assert_allclose(row, net.predict_logits(tokens[m], ctx), atol=1e-10)


def _brute_shapley(v, n):
    from math import factorial

    phi = np.zeros(n)
    for i in range(n):
        rest = [j for j in range(n) if j != i]
        for k in range(n):
            for s in combinations(rest, k):
                w = factorial(k) * factorial(n - k - 1) / factorial(n)
                phi[i] += w * (v(set(s) | {i}) - v(set(s)))
    return phi


def test_exact_shapley_matches_the_definition_and_adds_up():
    rng = np.random.default_rng(3)
    n = 5
    a, b = rng.standard_normal(n), rng.standard_normal((n, n))

    def v_set(s):
        x = np.array([i in s for i in range(n)], dtype=float)
        return float(a @ x + x @ b @ x + np.sin(x.sum()))

    def value(masks):
        return np.array([[v_set({i for i in range(n) if m[i]})] for m in masks])

    sh = exact_shapley(value, n)
    np.testing.assert_allclose(sh.phi[:, 0], _brute_shapley(v_set, n), atol=1e-12)
    np.testing.assert_allclose(sh.phi.sum(axis=0), sh.full - sh.base, atol=1e-12)


def test_sampled_shapley_converges_to_exact_and_adds_up():
    rng = np.random.default_rng(4)
    net = DeepSets._init(5, 1, 2, pooling="attention", seed=4)
    net.params["w_att"] = rng.standard_normal(net.d_embed)
    tokens = rng.standard_normal((9, 5))

    def value(masks):
        return masked_logits(net, tokens, masks, np.zeros(1))

    exact = exact_shapley(value, 9)
    est = sampled_shapley(value, 9, n_perm=4000)
    assert not est.exact and exact.exact
    np.testing.assert_allclose(est.phi.sum(axis=0), est.full - est.base, atol=1e-10)
    np.testing.assert_allclose(est.phi, exact.phi, atol=0.05 * np.abs(exact.phi).max())
    assert shapley(value, 9, max_exact=8).exact is False


def _rounds(rng, n):
    """El site lo decide dónde cae la smoke; el flash es ruido."""
    samples, targets = [], []
    for _ in range(n):
        site = rng.choice(["A", "B", "NoPlant"], p=[0.35, 0.35, 0.30])
        x = {"A": 200.0, "B": 800.0, "NoPlant": 500.0}[site]
        t = 90.0 if site == "NoPlant" else 6.0
        util = [
            {"util_type": "smoke", "x": x, "y": 500.0, "round_time_s": t, "side": "t"},
            {"util_type": "flash", "x": rng.uniform(100, 900), "y": 300.0,
             "round_time_s": 20.0, "side": "t"},
        ]
        samples.append({
            "tokens": round_tokens("de_mirage", util),
            "context": round_context(
                map_id="de_mirage", team=str(rng.choice(["NaVi", "G2"])), opponent="OPP",
                buy_type="full", equip_value=4000, utility=util, team_weapons="ak47,awp",
                opponent_weapons="m4a1", phase="regular",
            ),
        })
        targets.append(site)
    return samples, targets


def test_site_shap_credits_the_grenade_that_decides():
    rng = np.random.default_rng(5)
    samples, targets = _rounds(rng, 300)
    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 2})
    assert p.trained
    smoke, flash = [], []
    for s, y in zip(samples, targets, strict=True):
        if y not in ("A", "B"):
            continue
        sh = shapley(site_value(p, s["tokens"]), len(s["tokens"]))
        k = 0 if y == "A" else 1
        smoke.append(abs(sh.phi[0, k]))
        flash.append(abs(sh.phi[1, k]))
        full = p.site_net.predict_proba(_to_array(s["tokens"]), np.zeros(1))
        np.testing.assert_allclose(sh.full, full, atol=1e-10)
    # un flash solo está fuera de distribución (todas las rondas llevan los dos): se compara la media
    assert np.mean(smoke) > 2 * np.mean(flash)


def test_gate_full_coalition_reproduces_the_prediction():
    rng = np.random.default_rng(6)
    samples, targets = _rounds(rng, 300)
    p = SitePredictor.train(samples, targets, {"n_rounds": len(samples), "n_teams": 2})
    for s in samples[:10]:
        value, players = gate_value(p, s["tokens"], s["context"])
        assert players[-len(CONTEXT_GROUPS):] == list(CONTEXT_GROUPS)
        n = len(players)
        x_ctx = p.gate_vec.transform([s["context"]])[0]
        want = p.gate_net.predict_proba(_to_array(s["tokens"]), x_ctx)
        np.testing.assert_allclose(value(np.ones((1, n), bool))[0], want, atol=1e-10)
        sh = shapley(value, n)
        np.testing.assert_allclose(sh.phi.sum(axis=0), sh.full - sh.base, atol=1e-10)


def test_lower_level_grenades_get_the_lower_level_callout():
    from app.analytics.maps import _CALIBRATION, classify_point, lower_level_threshold

    pos_x, pos_y, scale = _CALIBRATION["de_nuke"]
    thr = lower_level_threshold("de_nuke")
    differs = 0
    for wx, wy in [(-500.0, -700.0), (400.0, -1000.0), (700.0, -600.0), (-300.0, -1300.0)]:
        x, y = (wx - pos_x) / scale, (pos_y - wy) / scale
        lower = classify_point("de_nuke", wx, wy, thr - 1.0)
        upper = classify_point("de_nuke", wx, wy)
        assert token_zone("de_nuke", x, y, 1.0).id == lower.id
        assert token_zone("de_nuke", x, y, 0.0).id == upper.id
        differs += lower.id != upper.id
    assert differs  # sin el nivel, abajo y arriba caerían en el mismo callout
