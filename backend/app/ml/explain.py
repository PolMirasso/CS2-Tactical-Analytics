# Refs https://arxiv.org/abs/1705.07874 (SHAP) y Castro et al. 2009 (Shapley por permutaciones)
"""Valores de Shapley para las cabezas de DeepSets.

Cada granada de la ronda es un jugador. Quitar una granada es la misma ronda sin ella, que un
modelo de conjuntos lee tal cual, así que no hace falta un baseline artificial: la coalición
vacía es la ronda sin utility. La gate tiene además jugadores de contexto (equipo, economía,
armas, fase); quitar uno lo deja en lo que manda la app con "Cualquiera".

Hasta ``MAX_EXACT`` jugadores se evalúan todas las coaliciones (Shapley exacto). Por encima, se
estiman con permutaciones aleatorias, emparejadas con su inversa.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import factorial

import numpy as np

from app.domain.weapons import WEAPON_IDS
from app.ml.deepsets import DeepSets
from app.ml.features import _OPENING_WINDOW_S, _UTILS, _WEAPON_NEUTRAL, ROUND_TIME_S
from app.ml.model import SitePredictor, _to_array

MAX_EXACT = 20
N_PERMUTATIONS = 512
_CHUNK = 1 << 15

# máscaras (B, n_jugadores) bool → salidas (B, K)
ValueFn = Callable[[np.ndarray], np.ndarray]

# jugadores de contexto de la gate → sus claves y el valor "Cualquiera" que toman al quitarlos
CONTEXT_GROUPS: dict[str, tuple[str, ...]] = {
    "team": ("team", "opponent"),
    "economy": ("buy", "equip", "opp_buy", "opp_equip"),
    "weapons": ("w_t_", "w_ct_"),
    "phase": ("phase",),
}
_NEUTRAL = {
    "team": "?", "opponent": "?", "buy": "?", "opp_buy": "?", "phase": "?",
    "equip": _WEAPON_NEUTRAL, "opp_equip": _WEAPON_NEUTRAL,
}


@dataclass
class Shapley:
    phi: np.ndarray  # (n_jugadores, K)
    base: np.ndarray  # (K,) salida sin ningún jugador
    full: np.ndarray  # (K,) salida con todos
    exact: bool


def masked_logits(
    net: DeepSets, tokens: np.ndarray, masks: np.ndarray, ctx: np.ndarray
) -> np.ndarray:
    """Logits de ``net`` sobre cada subconjunto de ``tokens`` que marca ``masks`` (B, n), en un
    solo batch. ``ctx`` es una fila común a todos o una fila por subconjunto."""
    p = net.params
    act, _ = net._act()
    masks = np.atleast_2d(np.asarray(masks, dtype=float))
    b = masks.shape[0]
    if tokens.shape[0]:
        a = tokens
        for i in range(1, net.phi_depth + 1):
            z = a @ p[f"W{i}"] + p[f"b{i}"]
            a = act(z) if i < net.phi_depth else z
        mode = getattr(net, "pooling", "mean")
        if mode == "attention":
            s = a @ p["w_att"] + p["b_att"]
            w = np.exp(s - s.max()) * masks
        else:
            w = masks
        pooled = w @ a
        if mode != "sum":
            tot = w.sum(axis=1, keepdims=True)
            pooled = pooled / np.where(tot > 0, tot, 1.0)
    else:
        pooled = np.zeros((b, net.d_embed))

    ctx = np.asarray(ctx, dtype=float)
    ctx = np.broadcast_to(ctx, (b, ctx.shape[-1])) if ctx.ndim == 1 else ctx
    a = np.hstack([pooled, ctx])
    for i in range(1, net.rho_depth + 1):
        z = a @ p[f"U{i}"] + p[f"c{i}"]
        a = act(z) if i < net.rho_depth else z
    return a


def masked_proba(
    net: DeepSets, tokens: np.ndarray, masks: np.ndarray, ctx: np.ndarray
) -> np.ndarray:
    z = masked_logits(net, tokens, masks, ctx) / (getattr(net, "temperature", 1.0) or 1.0)
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def _all_masks(n: int, start: int, stop: int) -> np.ndarray:
    idx = np.arange(start, stop, dtype=np.int64)
    return ((idx[:, None] >> np.arange(n)) & 1).astype(bool)


def exact_shapley(value: ValueFn, n: int) -> Shapley:
    total = 1 << n
    v: np.ndarray | None = None
    for start in range(0, total, _CHUNK):
        out = value(_all_masks(n, start, min(total, start + _CHUNK)))
        if v is None:
            v = np.empty((total, out.shape[1]))
        v[start : start + len(out)] = out
    assert v is not None
    if n == 0:
        return Shapley(np.zeros((0, v.shape[1])), v[0], v[0], True)

    idx = np.arange(total, dtype=np.int64)
    size = np.bitwise_count(idx)
    w = np.array([factorial(s) * factorial(n - s - 1) / factorial(n) for s in range(n)])
    phi = np.empty((n, v.shape[1]))
    for i in range(n):
        without = idx[((idx >> i) & 1) == 0]
        phi[i] = w[size[without]] @ (v[without | (1 << i)] - v[without])
    return Shapley(phi, v[0], v[-1], True)


def sampled_shapley(value: ValueFn, n: int, n_perm: int = N_PERMUTATIONS, seed: int = 0) -> Shapley:
    rng = np.random.default_rng(seed)
    half = [rng.permutation(n) for _ in range((n_perm + 1) // 2)]
    perms = np.array(half + [p[::-1] for p in half])
    # eslabón k de la permutación p = sus k primeros jugadores
    rank = np.argsort(perms, axis=1)
    masks = rank[:, None, :] < np.arange(n + 1)[None, :, None]
    v = value(masks.reshape(-1, n)).reshape(len(perms), n + 1, -1)
    phi = np.zeros((n, v.shape[2]))
    np.add.at(phi, perms, v[:, 1:] - v[:, :-1])
    return Shapley(phi / len(perms), v[0, 0], v[0, -1], False)


def shapley(value: ValueFn, n: int, max_exact: int = MAX_EXACT, seed: int = 0) -> Shapley:
    return exact_shapley(value, n) if n <= max_exact else sampled_shapley(value, n, seed=seed)


# cabezas

_DUMMY = np.zeros(1)


def site_value(model: SitePredictor, tokens) -> ValueFn:
    """[P(A), P(B)] de la cabeza de site; jugadores = granadas."""
    t = _to_array(tokens)
    return lambda masks: masked_proba(model.site_net, t, masks, _DUMMY)


def timing_value(model: SitePredictor, tokens) -> ValueFn:
    """P(cada una de ``model.timing_classes``); jugadores = granadas."""
    t = _to_array(tokens)
    return lambda masks: masked_proba(model.timing_net, t, masks, _DUMMY)


def _group_of(key: str) -> str | None:
    for g, keys in CONTEXT_GROUPS.items():
        if any(key == k or (k.endswith("_") and key.startswith(k)) for k in keys):
            return g
    return None


def _without(ctx: dict, removed: set[str]) -> dict:
    out = {}
    for k, v in ctx.items():
        g = _group_of(k)
        if g in removed:
            if g == "weapons":
                continue
            out[k] = _NEUTRAL[k]
        else:
            out[k] = v
    if "weapons" in removed:
        for side in ("t", "ct"):
            for wid in WEAPON_IDS:
                out[f"w_{side}_{wid}"] = _WEAPON_NEUTRAL
    return out


def gate_value(model: SitePredictor, tokens, context: dict) -> tuple[ValueFn, list[str]]:
    """[P(plant), P(NoPlant)] de la gate; jugadores = granadas y después ``CONTEXT_GROUPS``.

    Los conteos y tiempos de utility del contexto siguen a las granadas de la coalición, así
    que una granada quitada también sale de esas features."""
    t = _to_array(tokens)
    n = t.shape[0]
    groups = list(CONTEXT_GROUPS)
    vec = model.gate_vec
    col = {name: j for j, name in enumerate(vec.feature_names_)}

    rows = np.array([
        vec.transform([_without(context, {g for b, g in enumerate(groups) if not (m >> b) & 1})])[0]
        for m in range(1 << len(groups))
    ], dtype=float)

    kind = np.argmax(t[:, : len(_UTILS)], axis=1) if n else np.zeros(0, int)
    t01 = t[:, 6] if n else np.zeros(0)
    opening = (t01 * ROUND_TIME_S <= _OPENING_WINDOW_S).astype(float)
    util_cols = [(col.get(f"u_{u}"), kind == k) for k, u in enumerate(_UTILS)]

    def value(masks: np.ndarray) -> np.ndarray:
        g_mask, c_mask = masks[:, :n], masks[:, n:]
        ctx = rows[c_mask.astype(np.int64) @ (1 << np.arange(len(groups)))]
        gm = g_mask.astype(float)
        cnt = gm.sum(axis=1)
        derived = {
            "n_util": cnt,
            "n_opening": gm @ opening,
            "t_min": np.where(cnt > 0, np.where(g_mask, t01, np.inf).min(axis=1), 0.0)
            if n else np.zeros(len(masks)),
            "t_mean": (gm @ t01) / np.where(cnt > 0, cnt, 1.0),
        }
        for j, is_kind in util_cols:
            if j is not None:
                ctx[:, j] = gm @ is_kind.astype(float)
        for name, vals in derived.items():
            if name in col:
                ctx[:, col[name]] = vals
        return masked_proba(model.gate_net, t, g_mask, ctx)

    return value, [f"g{i}" for i in range(n)] + groups
