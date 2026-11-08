# Refs https://arxiv.org/abs/1602.04938 (LIME, Ribeiro et al. 2016), https://github.com/marcotcr/lime
"""LIME para las cabezas de DeepSets.

Como ``LimeTextExplainer``, con granadas en lugar de palabras: cada muestra es la ronda sin
algunas granadas (se quitan de 1 a n, al azar), pesada por su distancia coseno a la ronda entera,
y se ajusta una ridge sobre la presencia de cada granada. Los valores por defecto son los de la
librería.

``kernel_shap`` ajusta el mismo modelo lineal sobre las mismas muestras con el núcleo de Shapley
y la restricción de eficiencia (KernelSHAP, Lundberg y Lee 2017): LIME y SHAP solo se diferencian
en cómo pesan cada coalición.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import comb

import numpy as np

NUM_SAMPLES = 5000
KERNEL_WIDTH = 25.0
ALPHA = 1.0


@dataclass
class Linear:
    coef: np.ndarray  # (n,)
    intercept: float
    score: float  # R² ponderado del modelo lineal sobre las muestras
    local_pred: float  # su predicción para la ronda entera


def sample_masks(n: int, num_samples: int, rng: np.random.Generator) -> np.ndarray:
    """Fila 0 = la ronda entera; en las demás se quitan k ~ U{1..n} granadas al azar."""
    masks = np.ones((num_samples, n), dtype=bool)
    if n == 0 or num_samples < 2:
        return masks
    k = rng.integers(1, n + 1, num_samples - 1)
    keys = rng.random((num_samples - 1, n))
    cut = np.sort(keys, axis=1)[np.arange(num_samples - 1), k - 1]
    masks[1:] = keys > cut[:, None]
    return masks


def lime_weights(masks: np.ndarray, kernel_width: float = KERNEL_WIDTH) -> np.ndarray:
    """Núcleo exponencial sobre la distancia coseno (×100) a la ronda entera."""
    n = masks.shape[1]
    k = masks.sum(axis=1)
    d = (1.0 - np.sqrt(k / n)) * 100.0 if n else np.zeros(len(masks))
    return np.sqrt(np.exp(-(d**2) / kernel_width**2))


def weighted_ridge(x: np.ndarray, y: np.ndarray, w: np.ndarray, alpha: float) -> Linear:
    """``sklearn.linear_model.Ridge(alpha).fit(x, y, sample_weight=w)``, con su R²."""
    x = np.asarray(x, dtype=float)
    sw = w / w.sum()
    xm, ym = sw @ x, sw @ y
    xc, yc = x - xm, y - ym
    a = xc.T @ (w[:, None] * xc) + alpha * np.eye(x.shape[1])
    coef = np.linalg.solve(a, xc.T @ (w * yc))
    intercept = float(ym - xm @ coef)
    res = w @ (y - x @ coef - intercept) ** 2
    tot = w @ yc**2
    score = 1.0 - res / tot if tot > 0 else float(res == 0)
    return Linear(coef, intercept, float(score), float(x[0] @ coef + intercept))


def lime_fit(
    masks: np.ndarray, y: np.ndarray, kernel_width: float = KERNEL_WIDTH, alpha: float = ALPHA
) -> Linear:
    return weighted_ridge(masks, y, lime_weights(masks, kernel_width), alpha)


def kernel_shap(
    masks: np.ndarray, y: np.ndarray, v_empty: float, v_full: float, lime_sampled: bool = True
) -> np.ndarray:
    """φ por regresión con el núcleo de Shapley, con Σφ = v_full − v_empty impuesto.

    Con ``lime_sampled`` las coaliciones vienen de ``sample_masks`` y el peso es el núcleo
    dividido por la probabilidad de muestrearlas; si no, cada coalición cuenta una vez."""
    n = masks.shape[1]
    delta = v_full - v_empty
    if n <= 1:
        return np.full(n, delta)
    k = masks.sum(axis=1)
    keep = (k > 0) & (k < n)
    z, k = masks[keep].astype(float), k[keep]
    w = 1.0 / (k * (n - k))
    if not lime_sampled:
        w = w * (n - 1) / np.array([comb(n, int(s)) for s in k])
    # se elimina la última granada con la restricción: φ_n = delta − Σ φ_j
    x = z[:, :-1] - z[:, -1:]
    t = y[keep] - v_empty - z[:, -1] * delta
    sw = np.sqrt(w)
    beta = np.linalg.lstsq(x * sw[:, None], t * sw, rcond=None)[0]
    return np.append(beta, delta - beta.sum())


def lime(
    value: Callable[[np.ndarray], np.ndarray],
    n: int,
    label: int = 1,
    num_samples: int = NUM_SAMPLES,
    seed: int = 0,
) -> Linear:
    """LIME de la salida ``label`` de ``value`` (máscaras → salidas, como en ``explain``)."""
    masks = sample_masks(n, num_samples, np.random.default_rng(seed))
    return lime_fit(masks, value(masks)[:, label])
