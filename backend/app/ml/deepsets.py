# Refs https://arxiv.org/abs/1703.06114 y https://arxiv.org/abs/1612.00593
"""DeepSets site classifier (pure NumPy): predict the plant site from a round's
set of utility, no matter how many grenades or in what order.

    site = ρ( pool_i φ(token_i) ⊕ context )

From the papers (lightly adapted):
  Deep Sets - "a function f(X) [...] is invariant to the permutation of instances
  in X, iff it can be decomposed in the form ρ(Σ_{x∈X} φ(x))."
  PointNet - "the key [...] is the use of a single symmetric function, max
  pooling [...] invariant to input permutation."

So: a shared encoder φ embeds each grenade token, a symmetric pool over the set
makes it order/count-invariant, the pooled vector is concatenated with the round
context, and the head ρ outputs per-site scores. Trained with hand-written
backprop + Adam - no GPU/torch needed; the sets are tiny so CPU trains in <1 s.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

POOLINGS = ("mean", "sum", "attention")


def _relu(z: np.ndarray) -> np.ndarray:
    return np.maximum(z, 0.0)


def _d_relu(z: np.ndarray) -> np.ndarray:
    return (z > 0).astype(float)


def _tanh(z: np.ndarray) -> np.ndarray:
    return np.tanh(z)


def _d_tanh(z: np.ndarray) -> np.ndarray:
    t = np.tanh(z)
    return 1.0 - t * t


_LEAK = 0.01


def _leaky_relu(z: np.ndarray) -> np.ndarray:
    return np.where(z > 0, z, _LEAK * z)


def _d_leaky_relu(z: np.ndarray) -> np.ndarray:
    return np.where(z > 0, 1.0, _LEAK)


# name -> (activation, derivative w.r.t. its pre-activation)
ACTIVATIONS = {
    "relu": (_relu, _d_relu),
    "tanh": (_tanh, _d_tanh),
    "leaky_relu": (_leaky_relu, _d_leaky_relu),
}


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / e.sum()


@dataclass
class DeepSets:
    params: dict[str, np.ndarray]
    n_classes: int
    token_dim: int
    ctx_dim: int
    d_embed: int
    h_phi: int
    h_rho: int
    pooling: str = "mean"
    temperature: float = 1.0
    activation: str = "relu"

    # init
    @classmethod
    def _init(
        cls,
        token_dim: int,
        ctx_dim: int,
        n_classes: int,
        *,
        h_phi: int = 32,
        d_embed: int = 24,
        h_rho: int = 32,
        phi_depth: int = 2,
        rho_depth: int = 2,
        activation: str = "relu",
        pooling: str = "mean",
        seed: int = 0,
    ) -> DeepSets:
        """φ: token_dim →(h_phi ×phi_depth-1)→ d_embed;
        ρ: d_embed+ctx →(h_rho ×rho_depth-1)→ n_classes.

        The last layer of each block is linear. At the defaults (depth 2/2, relu)
        the params are the same keys, shapes and RNG draws as before the depth/
        activation knobs existed, so an already-persisted model still loads.
        """
        if pooling not in POOLINGS:
            raise ValueError(f"unknown pooling {pooling!r}, expected one of {POOLINGS}")
        if activation not in ACTIVATIONS:
            raise ValueError(
                f"unknown activation {activation!r}, expected one of {tuple(ACTIVATIONS)}"
            )
        if phi_depth < 1 or rho_depth < 1:
            raise ValueError("phi_depth and rho_depth must be >= 1")
        rng = np.random.default_rng(seed)

        # He for the rectifiers, Xavier for tanh
        gain = 1.0 if activation == "tanh" else 2.0

        def w(fan_in: int, fan_out: int) -> np.ndarray:
            return rng.standard_normal((fan_in, fan_out)) * np.sqrt(gain / fan_in)

        params: dict[str, np.ndarray] = {}
        phi_dims = [token_dim] + [h_phi] * (phi_depth - 1) + [d_embed]
        for i in range(phi_depth):
            params[f"W{i + 1}"] = w(phi_dims[i], phi_dims[i + 1])
            params[f"b{i + 1}"] = np.zeros(phi_dims[i + 1])
        rho_dims = [d_embed + ctx_dim] + [h_rho] * (rho_depth - 1) + [n_classes]
        for i in range(rho_depth):
            params[f"U{i + 1}"] = w(rho_dims[i], rho_dims[i + 1])
            params[f"c{i + 1}"] = np.zeros(rho_dims[i + 1])
        if pooling == "attention":
            # small init ⇒ near-uniform attention at start (≈ mean), then learns
            params["w_att"] = rng.standard_normal(d_embed) * 0.01
            params["b_att"] = np.zeros(())
        return cls(
            params, n_classes, token_dim, ctx_dim, d_embed, h_phi, h_rho,
            pooling=pooling, activation=activation,
        )

    @property
    def phi_depth(self) -> int:
        return sum(1 for k in self.params if k[:1] == "W" and k[1:].isdigit())

    @property
    def rho_depth(self) -> int:
        return sum(1 for k in self.params if k[:1] == "U" and k[1:].isdigit())

    def _act(self):
        return ACTIVATIONS[getattr(self, "activation", "relu")]

    @property
    def layers(self) -> str:
        pool = getattr(self, "pooling", "mean")
        act = getattr(self, "activation", "relu")
        phi = [self.token_dim]
        phi += [self.params[f"W{i}"].shape[1] for i in range(1, self.phi_depth + 1)]
        rho = [self.params[f"U{i}"].shape[1] for i in range(1, self.rho_depth + 1)]
        return (
            "φ" + "→".join(str(d) for d in phi) + f" · {pool} · "
            "ρ" + "→".join(str(d) for d in rho) + f" · {act}"
        )

    # pooling
    def _pool(self, z2: np.ndarray):
        """z2: (nt, d) token embeddings → pooled (d,) and a cache for backward."""
        mode = getattr(self, "pooling", "mean")
        nt = z2.shape[0]
        if mode == "sum":
            return z2.sum(axis=0), ("sum", nt, None)
        if mode == "attention":
            scores = z2 @ self.params["w_att"] + self.params["b_att"]
            att = _softmax(scores)
            return att @ z2, ("attention", nt, (z2, att))
        return z2.mean(axis=0), ("mean", nt, None)

    def _pool_backward(self, dpooled: np.ndarray, cache):
        """Given dL/dpooled, return dL/dz2 (nt, d) and grads for the pool's own params."""
        mode, nt, extra = cache
        grads: dict[str, np.ndarray] = {}
        if mode == "sum":
            return np.tile(dpooled, (nt, 1)), grads
        if mode == "attention":
            z2, att = extra
            g_att = z2 @ dpooled  # dL/d att_i
            # softmax jacobian: ds = a ⊙ (g − a·g)
            dscores = att * (g_att - att @ g_att)
            dz2 = np.outer(att, dpooled) + np.outer(dscores, self.params["w_att"])
            grads["w_att"] = z2.T @ dscores
            grads["b_att"] = dscores.sum()
            return dz2, grads
        return np.tile(dpooled / nt, (nt, 1)), grads

    # forward
    def _forward(self, tokens: np.ndarray, ctx: np.ndarray):
        p = self.params
        act, _ = self._act()
        n_phi, n_rho = self.phi_depth, self.rho_depth

        if tokens.shape[0] > 0:
            a, phi_cache = tokens, []
            for i in range(1, n_phi + 1):
                z = a @ p[f"W{i}"] + p[f"b{i}"]
                phi_cache.append((a, z))
                a = act(z) if i < n_phi else z
            pooled, pcache = self._pool(a)
        else:
            phi_cache = None
            pooled, pcache = np.zeros(self.d_embed), ("mean", 0, None)

        a, rho_cache = np.concatenate([pooled, ctx]), []
        for i in range(1, n_rho + 1):
            z = a @ p[f"U{i}"] + p[f"c{i}"]
            rho_cache.append((a, z))
            a = act(z) if i < n_rho else z
        return a, (tokens, phi_cache, rho_cache, pcache)

    def predict_logits(self, tokens: np.ndarray, ctx: np.ndarray) -> np.ndarray:
        logits, _ = self._forward(tokens, ctx)
        return logits

    def predict_proba(self, tokens: np.ndarray, ctx: np.ndarray) -> np.ndarray:
        logits, _ = self._forward(tokens, ctx)
        t = getattr(self, "temperature", 1.0) or 1.0
        return _softmax(logits / t)

    # per-sample cross-entropy gradient (data term only; weight decay is in ``fit``)
    def _backward_one(self, tokens: np.ndarray, ctx: np.ndarray, y: int):
        logits, cache = self._forward(tokens, ctx)
        _, phi_cache, rho_cache, pcache = cache
        _, dact = self._act()
        probs = _softmax(logits)
        grads = {k: np.zeros_like(v) for k, v in self.params.items()}

        d = probs.copy()
        d[y] -= 1.0
        n_rho = self.rho_depth
        for i in range(n_rho, 0, -1):
            a_prev, z = rho_cache[i - 1]
            if i < n_rho:
                d = d * dact(z)
            grads[f"U{i}"] += np.outer(a_prev, d)
            grads[f"c{i}"] += d
            d = self.params[f"U{i}"] @ d
        dpooled = d[: self.d_embed]

        if tokens.shape[0] > 0:
            d, pool_grads = self._pool_backward(dpooled, pcache)
            n_phi = self.phi_depth
            for i in range(n_phi, 0, -1):
                a_prev, z = phi_cache[i - 1]
                if i < n_phi:
                    d = d * dact(z)
                grads[f"W{i}"] += a_prev.T @ d
                grads[f"b{i}"] += d.sum(axis=0)
                d = d @ self.params[f"W{i}"].T
            for k, g in pool_grads.items():
                grads[k] += g

        loss = float(-np.log(probs[y] + 1e-12))
        return loss, grads

    # calibration (temperature scaling)
    @staticmethod
    def _nll(logits: np.ndarray, y: np.ndarray, t: float) -> float:
        z = logits / t
        z = z - z.max(axis=1, keepdims=True)
        logsumexp = np.log(np.exp(z).sum(axis=1))
        logp = z[np.arange(len(y)), y] - logsumexp
        return float(-logp.mean())

    @staticmethod
    def fit_temperature(
        logits: np.ndarray, y: np.ndarray, *, lo: float = 0.05, hi: float = 10.0, iters: int = 60
    ) -> float:
        """Scalar T that minimises NLL(logits/T) on (logits, y). NLL is convex in
        1/T, so a golden-section search on T finds the single minimum. Returns 1.0
        when there is nothing to fit."""
        logits = np.asarray(logits, dtype=float)
        y = np.asarray(y)
        if len(y) < 2 or logits.ndim != 2:
            return 1.0
        gr = (np.sqrt(5.0) - 1.0) / 2.0
        a, b = lo, hi
        c, d = b - gr * (b - a), a + gr * (b - a)
        fc, fd = DeepSets._nll(logits, y, c), DeepSets._nll(logits, y, d)
        for _ in range(iters):
            if fc < fd:
                b, d, fd = d, c, fc
                c = b - gr * (b - a)
                fc = DeepSets._nll(logits, y, c)
            else:
                a, c, fc = c, d, fd
                d = a + gr * (b - a)
                fd = DeepSets._nll(logits, y, d)
        return float((a + b) / 2.0)

    # training
    @classmethod
    def fit(
        cls,
        token_sets: list[np.ndarray],
        ctx: np.ndarray,
        y: np.ndarray,
        n_classes: int,
        *,
        epochs: int = 500,
        lr: float = 5e-3,
        weight_decay: float = 1e-4,
        patience: int = 50,
        pooling: str = "mean",
        h_phi: int = 32,
        d_embed: int = 24,
        h_rho: int = 32,
        phi_depth: int = 2,
        rho_depth: int = 2,
        activation: str = "relu",
        seed: int = 0,
    ) -> tuple[DeepSets, float, np.ndarray]:
        """Fit on (token_sets, ctx, y) returns (model, validation_accuracy, val_idx)
        val_idx = rows held out for validation (empty when the set is too small to split)
        """
        n = len(token_sets)
        model = cls._init(
            token_sets[0].shape[1] if n else 7, ctx.shape[1], n_classes,
            h_phi=h_phi, d_embed=d_embed, h_rho=h_rho,
            phi_depth=phi_depth, rho_depth=rho_depth, activation=activation,
            pooling=pooling, seed=seed,
        )

        rng = np.random.default_rng(seed)
        idx = rng.permutation(n)
        n_val = 0 if n < 10 else max(2, n // 5)
        val_idx = idx[:n_val]
        tr_idx = idx[n_val:] if n_val else idx

        weight_keys = tuple(k for k in model.params if k[:1] in ("W", "U") and k[1:].isdigit())
        m = {k: np.zeros_like(v) for k, v in model.params.items()}
        v = {k: np.zeros_like(v) for k, v in model.params.items()}
        b1m, b2m = 0.9, 0.999
        step = 0
        best_acc = -1.0
        best_params: dict[str, np.ndarray] | None = None
        since_best = 0

        def accuracy(rows: np.ndarray) -> float:
            if len(rows) == 0:
                return 0.0
            ok = sum(
                int(np.argmax(model.predict_proba(token_sets[i], ctx[i])) == y[i]) for i in rows
            )
            return ok / len(rows)

        for _ in range(epochs):
            grads = {k: np.zeros_like(val) for k, val in model.params.items()}
            for i in tr_idx:
                _, g_i = model._backward_one(token_sets[i], ctx[i], y[i])
                for k in grads:
                    grads[k] += g_i[k]

            scale = 1.0 / max(1, len(tr_idx))
            step += 1
            for k, g in grads.items():
                g = g * scale
                if k in weight_keys:
                    g = g + weight_decay * model.params[k]
                m[k] = b1m * m[k] + (1 - b1m) * g
                v[k] = b2m * v[k] + (1 - b2m) * (g * g)
                mhat = m[k] / (1 - b1m**step)
                vhat = v[k] / (1 - b2m**step)
                model.params[k] -= lr * mhat / (np.sqrt(vhat) + 1e-8)

            acc = accuracy(val_idx) if n_val else accuracy(tr_idx)
            if acc > best_acc:
                best_acc = acc
                best_params = {k: val.copy() for k, val in model.params.items()}
                since_best = 0
            else:
                since_best += 1
                if since_best >= patience:
                    break

        if best_params is not None:
            model.params = best_params
        return model, float(best_acc), val_idx
