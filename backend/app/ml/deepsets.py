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
        pooling: str = "mean",
        seed: int = 0,
    ) -> DeepSets:
        if pooling not in POOLINGS:
            raise ValueError(f"unknown pooling {pooling!r}, expected one of {POOLINGS}")
        rng = np.random.default_rng(seed)

        def he(fan_in: int, fan_out: int) -> np.ndarray:
            return rng.standard_normal((fan_in, fan_out)) * np.sqrt(2.0 / fan_in)

        params = {
            "W1": he(token_dim, h_phi), "b1": np.zeros(h_phi),
            "W2": he(h_phi, d_embed), "b2": np.zeros(d_embed),
            "U1": he(d_embed + ctx_dim, h_rho), "c1": np.zeros(h_rho),
            "U2": he(h_rho, n_classes), "c2": np.zeros(n_classes),
        }
        if pooling == "attention":
            # small init ⇒ near-uniform attention at start (≈ mean), then learns
            params["w_att"] = rng.standard_normal(d_embed) * 0.01
            params["b_att"] = np.zeros(())
        return cls(params, n_classes, token_dim, ctx_dim, d_embed, h_phi, h_rho, pooling=pooling)

    @property
    def layers(self) -> str:
        pool = getattr(self, "pooling", "mean")
        return (
            f"φ{self.token_dim}→{self.h_phi}→{self.d_embed} · {pool} · "
            f"ρ{self.h_rho}→{self.n_classes}"
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
        if tokens.shape[0] > 0:
            z1 = tokens @ p["W1"] + p["b1"]
            a1 = _relu(z1)
            z2 = a1 @ p["W2"] + p["b2"]
            pooled, pcache = self._pool(z2)
        else:
            z1 = a1 = z2 = None
            pooled, pcache = np.zeros(self.d_embed), ("mean", 0, None)
        h = np.concatenate([pooled, ctx])
        zr1 = h @ p["U1"] + p["c1"]
        ar1 = _relu(zr1)
        logits = ar1 @ p["U2"] + p["c2"]
        cache = (tokens, z1, a1, z2, h, zr1, ar1, pcache)
        return logits, cache

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
        _, z1, a1, _, h, zr1, ar1, pcache = cache
        probs = _softmax(logits)
        grads = {k: np.zeros_like(v) for k, v in self.params.items()}

        dlogits = probs.copy()
        dlogits[y] -= 1.0
        grads["U2"] += np.outer(ar1, dlogits)
        grads["c2"] += dlogits
        dzr1 = (self.params["U2"] @ dlogits) * (zr1 > 0)
        grads["U1"] += np.outer(h, dzr1)
        grads["c1"] += dzr1
        dpooled = (self.params["U1"] @ dzr1)[: self.d_embed]

        if tokens.shape[0] > 0:
            dz2, pool_grads = self._pool_backward(dpooled, pcache)
            grads["W2"] += a1.T @ dz2
            grads["b2"] += dz2.sum(axis=0)
            dz1 = (dz2 @ self.params["W2"].T) * (z1 > 0)
            grads["W1"] += tokens.T @ dz1
            grads["b1"] += dz1.sum(axis=0)
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
        seed: int = 0,
    ) -> tuple[DeepSets, float, np.ndarray]:
        """Fit on (token_sets, ctx, y) returns (model, validation_accuracy, val_idx)
        val_idx = rows held out for validation (empty when the set is too small to split)
        """
        n = len(token_sets)
        model = cls._init(
            token_sets[0].shape[1] if n else 7, ctx.shape[1], n_classes, pooling=pooling, seed=seed
        )

        rng = np.random.default_rng(seed)
        idx = rng.permutation(n)
        n_val = 0 if n < 10 else max(2, n // 5)
        val_idx = idx[:n_val]
        tr_idx = idx[n_val:] if n_val else idx

        weight_keys = ("W1", "W2", "U1", "U2")
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
