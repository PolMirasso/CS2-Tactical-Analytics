# Refs https://arxiv.org/abs/1810.00825, https://arxiv.org/abs/1706.03762
"""Set Transformer site classifier (pure NumPy): predict the plant site from a round's
set of utility, no matter how many grenades or in what order.

    H⁰ = X·E
    SAB(H) = LN(M + rFF(M)),   M = LN(H + Multihead(H, H, H))
    site = ρ( pool_i SAB(…SAB(H⁰))_i ⊕ context )

Each grenade attends to every other one with a weight it learns (the GCN's Â, but
learned and per head). No positional encoding, so the encoder is permutation-equivariant
and the pooled readout invariant. Hand-written backprop + Adam, like DeepSets.
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


_LN_EPS = 1e-5


def _layer_norm(x: np.ndarray, g: np.ndarray, b: np.ndarray):
    xc = x - x.mean(axis=-1, keepdims=True)
    inv = 1.0 / np.sqrt((xc * xc).mean(axis=-1, keepdims=True) + _LN_EPS)
    xh = xc * inv
    return xh * g + b, (xh, inv)


def _layer_norm_backward(dy: np.ndarray, g: np.ndarray, cache):
    xh, inv = cache
    dxh = dy * g
    dx = inv * (dxh - dxh.mean(axis=-1, keepdims=True)
                - xh * (dxh * xh).mean(axis=-1, keepdims=True))
    return dx, (dy * xh).sum(axis=0), dy.sum(axis=0)


@dataclass
class SetTransformer:
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
    n_heads: int = 4
    layer_norm: bool = True
    attn_gate: bool = False

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
        n_heads: int = 4,
        layer_norm: bool = True,
        attn_gate: bool = False,
        seed: int = 0,
    ) -> SetTransformer:
        """Encoder: token_dim →E→ d_embed, then phi_depth SABs of width d_embed with
        n_heads heads and an rFF of width h_phi;
        ρ: d_embed+ctx →(h_rho ×rho_depth-1)→ n_classes, last layer linear.
        """
        if pooling not in POOLINGS:
            raise ValueError(f"unknown pooling {pooling!r}, expected one of {POOLINGS}")
        if activation not in ACTIVATIONS:
            raise ValueError(
                f"unknown activation {activation!r}, expected one of {tuple(ACTIVATIONS)}"
            )
        if phi_depth < 1 or rho_depth < 1:
            raise ValueError("phi_depth and rho_depth must be >= 1")
        if n_heads < 1 or d_embed % n_heads:
            raise ValueError(f"d_embed={d_embed} must split evenly into {n_heads} heads")
        rng = np.random.default_rng(seed)

        # He for the rectifiers, Xavier for tanh and for the linear projections
        gain = 1.0 if activation == "tanh" else 2.0

        def w(fan_in: int, fan_out: int, g: float = gain) -> np.ndarray:
            return rng.standard_normal((fan_in, fan_out)) * np.sqrt(g / fan_in)

        d = d_embed
        params: dict[str, np.ndarray] = {"E": w(token_dim, d, 1.0), "e": np.zeros(d)}
        for i in range(1, phi_depth + 1):
            # no key bias: it adds the same q·b_k to every key of a row, softmax ignores it
            params[f"Wq{i}"], params[f"bq{i}"] = w(d, d, 1.0), np.zeros(d)
            params[f"Wk{i}"] = w(d, d, 1.0)
            params[f"Wv{i}"], params[f"bv{i}"] = w(d, d, 1.0), np.zeros(d)
            params[f"Wo{i}"], params[f"bo{i}"] = w(d, d, 1.0), np.zeros(d)
            params[f"Wf{i}"], params[f"bf{i}"] = w(d, h_phi), np.zeros(h_phi)
            params[f"Wg{i}"], params[f"bg{i}"] = w(h_phi, d, 1.0), np.zeros(d)
            if attn_gate:
                # ReZero: starts at 0, so each SAB begins as DeepSets
                params[f"Ga{i}"] = np.zeros(())
            if layer_norm:
                for j in (1, 2):
                    params[f"ln{j}g{i}"], params[f"ln{j}b{i}"] = np.ones(d), np.zeros(d)
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
            pooling=pooling, activation=activation, n_heads=n_heads, layer_norm=layer_norm,
            attn_gate=attn_gate,
        )

    @property
    def phi_depth(self) -> int:
        return sum(1 for k in self.params if k[:2] == "Wq")

    @property
    def rho_depth(self) -> int:
        return sum(1 for k in self.params if k[:1] == "U" and k[1:].isdigit())

    @property
    def gates(self) -> list[float]:
        return [float(self.params[f"Ga{i}"]) for i in range(1, self.phi_depth + 1)
                if f"Ga{i}" in self.params]

    def _act(self):
        return ACTIVATIONS[self.activation]

    @property
    def layers(self) -> str:
        rho = [self.params[f"U{i}"].shape[1] for i in range(1, self.rho_depth + 1)]
        ln = ("+ln" if self.layer_norm else "") + ("+gate" if self.attn_gate else "")
        return (
            f"settf[{self.phi_depth}×sab·{self.n_heads}h{ln}]"
            f"{self.token_dim}→{self.d_embed}/{self.h_phi} · {self.pooling} · "
            "ρ" + "→".join(str(d) for d in rho) + f" · {self.activation}"
        )

    # encoder
    def _encode(self, x: np.ndarray):
        p = self.params
        act, _ = self._act()
        n, d, h = x.shape[0], self.d_embed, self.n_heads
        dh = d // h
        scale = 1.0 / np.sqrt(dh)

        def heads(m: np.ndarray) -> np.ndarray:
            return m.reshape(n, h, dh).transpose(1, 0, 2)

        a = x @ p["E"] + p["e"]
        cache = []
        for i in range(1, self.phi_depth + 1):
            qh = heads(a @ p[f"Wq{i}"] + p[f"bq{i}"])
            kh = heads(a @ p[f"Wk{i}"])
            vh = heads(a @ p[f"Wv{i}"] + p[f"bv{i}"])
            s = qh @ kh.transpose(0, 2, 1) * scale
            att = np.exp(s - s.max(axis=-1, keepdims=True))
            att /= att.sum(axis=-1, keepdims=True)
            o = (att @ vh).transpose(1, 0, 2).reshape(n, d)
            br = o @ p[f"Wo{i}"] + p[f"bo{i}"]
            m = a + (p[f"Ga{i}"] * br if self.attn_gate else br)
            ln1 = ln2 = None
            if self.layer_norm:
                m, ln1 = _layer_norm(m, p[f"ln1g{i}"], p[f"ln1b{i}"])
            zf = m @ p[f"Wf{i}"] + p[f"bf{i}"]
            gf = act(zf)
            out = m + gf @ p[f"Wg{i}"] + p[f"bg{i}"]
            if self.layer_norm:
                out, ln2 = _layer_norm(out, p[f"ln2g{i}"], p[f"ln2b{i}"])
            cache.append((a, qh, kh, vh, att, o, br, m, ln1, zf, gf, ln2))
            a = out
        return a, cache

    def _encode_backward(self, x: np.ndarray, d: np.ndarray, cache, grads) -> None:
        p = self.params
        _, dact = self._act()
        n, dm, h = x.shape[0], self.d_embed, self.n_heads
        dh = dm // h
        scale = 1.0 / np.sqrt(dh)

        def heads(m: np.ndarray) -> np.ndarray:
            return m.reshape(n, h, dh).transpose(1, 0, 2)

        def merge(m: np.ndarray) -> np.ndarray:
            return m.transpose(1, 0, 2).reshape(n, dm)

        for i in range(self.phi_depth, 0, -1):
            a, qh, kh, vh, att, o, br, m, ln1, zf, gf, ln2 = cache[i - 1]
            if self.layer_norm:
                d, dg, db = _layer_norm_backward(d, p[f"ln2g{i}"], ln2)
                grads[f"ln2g{i}"] += dg
                grads[f"ln2b{i}"] += db
            grads[f"Wg{i}"] += gf.T @ d
            grads[f"bg{i}"] += d.sum(axis=0)
            dz = (d @ p[f"Wg{i}"].T) * dact(zf)
            grads[f"Wf{i}"] += m.T @ dz
            grads[f"bf{i}"] += dz.sum(axis=0)
            d = d + dz @ p[f"Wf{i}"].T
            if self.layer_norm:
                d, dg, db = _layer_norm_backward(d, p[f"ln1g{i}"], ln1)
                grads[f"ln1g{i}"] += dg
                grads[f"ln1b{i}"] += db
            db = d
            if self.attn_gate:
                grads[f"Ga{i}"] += (d * br).sum()
                db = d * p[f"Ga{i}"]
            grads[f"Wo{i}"] += o.T @ db
            grads[f"bo{i}"] += db.sum(axis=0)
            doh = heads(db @ p[f"Wo{i}"].T)
            datt = doh @ vh.transpose(0, 2, 1)
            dvh = att.transpose(0, 2, 1) @ doh
            # softmax jacobian per row, then the 1/√d_h of the scores
            ds = att * (datt - (datt * att).sum(axis=-1, keepdims=True)) * scale
            dq, dk, dv = merge(ds @ kh), merge(ds.transpose(0, 2, 1) @ qh), merge(dvh)
            grads[f"Wq{i}"] += a.T @ dq
            grads[f"bq{i}"] += dq.sum(axis=0)
            grads[f"Wk{i}"] += a.T @ dk
            grads[f"Wv{i}"] += a.T @ dv
            grads[f"bv{i}"] += dv.sum(axis=0)
            d = d + dq @ p[f"Wq{i}"].T + dk @ p[f"Wk{i}"].T + dv @ p[f"Wv{i}"].T
        grads["E"] += x.T @ d
        grads["e"] += d.sum(axis=0)

    # pooling
    def _pool(self, z2: np.ndarray):
        """z2: (nt, d) token embeddings → pooled (d,) and a cache for backward."""
        mode = self.pooling
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
        n_rho = self.rho_depth

        if tokens.shape[0] > 0:
            z2, enc_cache = self._encode(tokens)
            pooled, pcache = self._pool(z2)
        else:
            enc_cache = None
            pooled, pcache = np.zeros(self.d_embed), ("mean", 0, None)

        a, rho_cache = np.concatenate([pooled, ctx]), []
        for i in range(1, n_rho + 1):
            z = a @ p[f"U{i}"] + p[f"c{i}"]
            rho_cache.append((a, z))
            a = act(z) if i < n_rho else z
        return a, (enc_cache, rho_cache, pcache)

    def predict_logits(self, tokens: np.ndarray, ctx: np.ndarray) -> np.ndarray:
        logits, _ = self._forward(tokens, ctx)
        return logits

    def predict_proba(self, tokens: np.ndarray, ctx: np.ndarray) -> np.ndarray:
        logits, _ = self._forward(tokens, ctx)
        t = self.temperature or 1.0
        return _softmax(logits / t)

    # per-sample cross-entropy gradient (data term only; weight decay is in ``fit``)
    def _backward_one(self, tokens: np.ndarray, ctx: np.ndarray, y: int):
        logits, (enc_cache, rho_cache, pcache) = self._forward(tokens, ctx)
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
            dz2, pool_grads = self._pool_backward(dpooled, pcache)
            self._encode_backward(tokens, dz2, enc_cache, grads)
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
        logits = np.asarray(logits, dtype=float)
        y = np.asarray(y)
        if len(y) < 2 or logits.ndim != 2:
            return 1.0
        gr = (np.sqrt(5.0) - 1.0) / 2.0
        a, b = lo, hi
        c, d = b - gr * (b - a), a + gr * (b - a)
        nll = SetTransformer._nll
        fc, fd = nll(logits, y, c), nll(logits, y, d)
        for _ in range(iters):
            if fc < fd:
                b, d, fd = d, c, fc
                c = b - gr * (b - a)
                fc = nll(logits, y, c)
            else:
                a, c, fc = c, d, fd
                d = a + gr * (b - a)
                fd = nll(logits, y, d)
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
        **arch_kw,
    ) -> tuple[SetTransformer, float, np.ndarray]:
        """Fit on (token_sets, ctx, y) returns (model, validation_accuracy, val_idx)
        val_idx = rows held out for validation (empty when the set is too small to split)
        """
        n = len(token_sets)
        model = cls._init(
            token_sets[0].shape[1] if n else 7, ctx.shape[1], n_classes,
            h_phi=h_phi, d_embed=d_embed, h_rho=h_rho,
            phi_depth=phi_depth, rho_depth=rho_depth, activation=activation,
            pooling=pooling, seed=seed, **arch_kw,
        )

        rng = np.random.default_rng(seed)
        idx = rng.permutation(n)
        n_val = 0 if n < 10 else max(2, n // 5)
        val_idx = idx[:n_val]
        tr_idx = idx[n_val:] if n_val else idx

        # matrices and the attention gate only: biases, LayerNorm gains and the attention
        # readout are not decayed
        weight_keys = tuple(k for k in model.params if k[:1] in ("W", "U", "E", "G"))
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
