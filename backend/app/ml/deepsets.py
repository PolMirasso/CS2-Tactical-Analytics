# Refs https://arxiv.org/abs/1703.06114 y https://arxiv.org/abs/1612.00593
"""DeepSets site classifier (pure NumPy): predict the plant site from a round's
set of utility, no matter how many grenades or in what order.

    site = ρ( mean_i φ(token_i) ⊕ context )

From the papers (lightly adapted):
  Deep Sets - "a function f(X) [...] is invariant to the permutation of instances
  in X, iff it can be decomposed in the form ρ(Σ_{x∈X} φ(x))."
  PointNet - "the key [...] is the use of a single symmetric function, max
  pooling [...] invariant to input permutation."

So: a shared encoder φ embeds each grenade token, a symmetric pool over the set
makes it order/count-invariant (we use the mean, not sum/max), the pooled vector
is concatenated with the round context, and the head ρ outputs per-site scores.
Trained with hand-written backprop + Adam - no GPU/torch needed; the sets are
tiny so CPU trains in under a second.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
        seed: int = 0,
    ) -> DeepSets:
        rng = np.random.default_rng(seed)

        def he(fan_in: int, fan_out: int) -> np.ndarray:
            return rng.standard_normal((fan_in, fan_out)) * np.sqrt(2.0 / fan_in)

        params = {
            "W1": he(token_dim, h_phi), "b1": np.zeros(h_phi),
            "W2": he(h_phi, d_embed), "b2": np.zeros(d_embed),
            "U1": he(d_embed + ctx_dim, h_rho), "c1": np.zeros(h_rho),
            "U2": he(h_rho, n_classes), "c2": np.zeros(n_classes),
        }
        return cls(params, n_classes, token_dim, ctx_dim, d_embed, h_phi, h_rho)

    @property
    def layers(self) -> str:
        return f"φ{self.token_dim}→{self.h_phi}→{self.d_embed} · ρ{self.h_rho}→{self.n_classes}"

    # forward
    def _forward(self, tokens: np.ndarray, ctx: np.ndarray):
        p = self.params
        if tokens.shape[0] > 0:
            z1 = tokens @ p["W1"] + p["b1"]
            a1 = _relu(z1)
            z2 = a1 @ p["W2"] + p["b2"]
            pooled = z2.mean(axis=0)
        else:
            z1 = a1 = z2 = None
            pooled = np.zeros(self.d_embed)
        h = np.concatenate([pooled, ctx])
        zr1 = h @ p["U1"] + p["c1"]
        ar1 = _relu(zr1)
        logits = ar1 @ p["U2"] + p["c2"]
        cache = (tokens, z1, a1, z2, h, zr1, ar1)
        return logits, cache

    def predict_proba(self, tokens: np.ndarray, ctx: np.ndarray) -> np.ndarray:
        logits, _ = self._forward(tokens, ctx)
        return _softmax(logits)

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
        seed: int = 0,
    ) -> tuple[DeepSets, float, np.ndarray]:
        """Fit on (token_sets, ctx, y) returns (model, validation_accuracy, val_idx) 
        val_idx are the row indices held out for validation (empty when the set was too small to split)
        """
        n = len(token_sets)
        model = cls._init(token_sets[0].shape[1] if n else 7, ctx.shape[1], n_classes, seed=seed)

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
            ok = sum(int(np.argmax(model.predict_proba(token_sets[i], ctx[i])) == y[i]) for i in rows)
            return ok / len(rows)

        for _ in range(epochs):
            grads = {k: np.zeros_like(val) for k, val in model.params.items()}
            for i in tr_idx:
                tokens, ctx_i = token_sets[i], ctx[i]
                logits, cache = model._forward(tokens, ctx_i)
                _, z1, a1, _, h, zr1, ar1 = cache
                probs = _softmax(logits)

                dlogits = probs.copy()
                dlogits[y[i]] -= 1.0
                grads["U2"] += np.outer(ar1, dlogits)
                grads["c2"] += dlogits
                dzr1 = (model.params["U2"] @ dlogits) * (zr1 > 0)
                grads["U1"] += np.outer(h, dzr1)
                grads["c1"] += dzr1
                dpooled = (model.params["U1"] @ dzr1)[: model.d_embed]

                nt = tokens.shape[0]
                if nt > 0:
                    dz2 = np.tile(dpooled / nt, (nt, 1))
                    grads["W2"] += a1.T @ dz2
                    grads["b2"] += dz2.sum(axis=0)
                    dz1 = (dz2 @ model.params["W2"].T) * (z1 > 0)
                    grads["W1"] += tokens.T @ dz1
                    grads["b1"] += dz1.sum(axis=0)

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
