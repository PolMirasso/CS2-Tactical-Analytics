from __future__ import annotations

import numpy as np

from app.ml.anchors import ANY, Pool, find_anchor, round_predicates, wilson_lower
from app.ml.features import round_tokens


def test_wilson_lower_bound():
    assert wilson_lower(0, 0) == 0.0
    assert wilson_lower(10, 10) < wilson_lower(100, 100) < 1.0
    assert 0.94 < wilson_lower(32, 32) < 0.96
    assert wilson_lower(90, 100) < 0.9


def _pool(rng, n=400):
    """El modelo dice B cuando hay smoke en Z1; el flash en Z2 es ruido."""
    preds, ps = [], []
    for _ in range(n):
        s = set()
        signal = rng.random() < 0.3
        if signal:
            s |= {("smoke", "Z1"), (ANY, "Z1")}
        if rng.random() < 0.5:
            s |= {("flash", "Z2"), (ANY, "Z2")}
        if rng.random() < 0.5:
            s |= {("molotov", "Z3"), (ANY, "Z3")}
        ps.append(s)
        preds.append(1 if signal or rng.random() < 0.3 else 0)
    return Pool.build(ps, preds), ps


def test_anchor_finds_the_condition_that_decides():
    pool, _ = _pool(np.random.default_rng(0))
    x = {("smoke", "Z1"), (ANY, "Z1"), ("flash", "Z2"), (ANY, "Z2")}
    a = find_anchor(pool, x, target=1)
    assert a.valid and a.precision == 1.0
    assert {z for _, z in a.predicates} == {"Z1"}
    assert a.coverage > 0.2


def test_no_anchor_when_nothing_explains_it():
    pool, _ = _pool(np.random.default_rng(1))
    a = find_anchor(pool, {("flash", "Z2"), (ANY, "Z2")}, target=0, max_size=2)
    assert a is not None and not a.valid


def test_anchor_never_repeats_a_callout_with_and_without_type():
    pool, ps = _pool(np.random.default_rng(2))
    for x in ps[:30]:
        a = find_anchor(pool, x, target=1, tau=0.999, max_size=3)
        if a is None:
            continue
        for t, z in a.predicates:
            if t == ANY:
                assert not any(q == z and u != ANY for u, q in a.predicates)


def test_round_predicates_use_the_level_on_nuke():
    util = [{"util_type": "smoke", "x": 300.0, "y": 700.0, "round_time_s": 5, "side": "t"}]
    up = round_predicates("de_nuke", round_tokens("de_nuke", util))
    tokens = round_tokens("de_nuke", util)
    tokens[0][7] = 1.0
    down = round_predicates("de_nuke", tokens)
    assert ("smoke", next(z for t, z in up if t == "smoke")) in up
    assert {z for _, z in up} != {z for _, z in down}
