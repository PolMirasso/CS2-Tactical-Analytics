from __future__ import annotations

import numpy as np
import pytest
from sklearn.linear_model import Ridge
from sklearn.metrics.pairwise import cosine_distances

from app.ml.deepsets import DeepSets
from app.ml.explain import exact_shapley, masked_proba
from app.ml.lime import (
    kernel_shap,
    lime,
    lime_fit,
    lime_weights,
    sample_masks,
    weighted_ridge,
)


def test_sample_masks_follow_lime_text():
    masks = sample_masks(6, 20000, np.random.default_rng(0))
    assert masks[0].all()
    removed = (~masks[1:]).sum(axis=1)
    assert removed.min() == 1 and removed.max() == 6
    counts = np.bincount(removed, minlength=7)[1:] / len(removed)
    np.testing.assert_allclose(counts, 1 / 6, atol=0.015)
    # cada granada se quita con la misma frecuencia
    np.testing.assert_allclose((~masks[1:]).mean(axis=0), (~masks[1:]).mean(), atol=0.015)


def test_lime_weights_match_the_library_kernel():
    masks = sample_masks(7, 200, np.random.default_rng(1))
    d = cosine_distances(masks[:1].astype(float), masks.astype(float))[0] * 100
    np.testing.assert_allclose(lime_weights(masks), np.sqrt(np.exp(-(d**2) / 25.0**2)))


def test_weighted_ridge_matches_sklearn():
    rng = np.random.default_rng(2)
    x = rng.random((300, 5)) > 0.4
    y = rng.standard_normal(300)
    w = rng.random(300)
    got = weighted_ridge(x, y, w, alpha=1.0)
    ref = Ridge(alpha=1.0).fit(x, y, sample_weight=w)
    np.testing.assert_allclose(got.coef, ref.coef_, atol=1e-10)
    assert got.intercept == pytest.approx(ref.intercept_, abs=1e-10)
    assert got.score == pytest.approx(ref.score(x, y, sample_weight=w), abs=1e-10)
    assert got.local_pred == pytest.approx(ref.predict(x[:1])[0], abs=1e-10)


def test_lime_recovers_an_additive_model():
    a = np.array([0.3, -0.2, 0.05, 0.0])
    masks = sample_masks(4, 500, np.random.default_rng(3))
    fit = lime_fit(masks, 0.1 + masks @ a, alpha=0.0)
    np.testing.assert_allclose(fit.coef, a, atol=1e-10)
    assert fit.score == pytest.approx(1.0)


def _net_value(n, seed):
    rng = np.random.default_rng(seed)
    net = DeepSets._init(5, 1, 2, pooling="attention", seed=seed)
    net.params["w_att"] = rng.standard_normal(net.d_embed)
    tokens = rng.standard_normal((n, 5))
    return lambda masks: masked_proba(net, tokens, masks, np.zeros(1))


def test_kernel_shap_over_every_coalition_is_exact_shapley():
    value = _net_value(7, 4)
    exact = exact_shapley(value, 7)
    masks = ((np.arange(1 << 7)[:, None] >> np.arange(7)) & 1).astype(bool)
    y = value(masks)[:, 1]
    phi = kernel_shap(masks, y, y[0], y[-1], lime_sampled=False)
    np.testing.assert_allclose(phi, exact.phi[:, 1], atol=1e-10)


def test_kernel_shap_on_lime_samples_converges_to_exact():
    value = _net_value(9, 5)
    exact = exact_shapley(value, 9).phi[:, 1]
    masks = sample_masks(9, 40000, np.random.default_rng(6))
    y = value(masks)[:, 1]
    v_empty = value(np.zeros((1, 9), dtype=bool))[0, 1]
    phi = kernel_shap(masks, y, v_empty, y[0])
    assert phi.sum() == pytest.approx(y[0] - v_empty)
    np.testing.assert_allclose(phi, exact, atol=0.1 * np.abs(exact).max())


def test_lime_on_a_deepsets_round():
    rng = np.random.default_rng(7)
    net = DeepSets._init(5, 1, 2, seed=7)
    tokens = rng.standard_normal((6, 5))

    def value(masks):
        return masked_proba(net, tokens, masks, np.zeros(1))

    fit = lime(value, 6, seed=0)
    assert fit.coef.shape == (6,)
    assert fit.local_pred == pytest.approx(value(np.ones((1, 6), bool))[0, 1], abs=0.1)
    again = lime(value, 6, seed=0)
    np.testing.assert_array_equal(fit.coef, again.coef)
