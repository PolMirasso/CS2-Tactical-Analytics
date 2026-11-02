# Refs https://ojs.aaai.org/index.php/AAAI/article/view/11491 (Anchors, Ribeiro et al. 2018)
"""Anchors para la cabeza de site.

Una regla es un conjunto de condiciones como "hay una smoke en B Doors" o "hay utility en
B Doors", sacadas de las granadas de la ronda. Su precisión es la fracción de rondas reales del
mismo mapa que cumplen la regla en las que el modelo predice el mismo site, y su cobertura, la
fracción de rondas del mapa que la cumplen. Se busca la regla de más cobertura cuya precisión
supera ``TAU`` con confianza (cota inferior de Wilson), con búsqueda en haz por tamaño como en el
artículo. Como las rondas son finitas, la precisión se calcula entera y no hace falta el bandit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.ml.explain import token_zone
from app.ml.features import _UTILS

TAU = 0.95
Z_ONE_SIDED = 1.2816  # confianza del 90 %, el δ = 0.1 del artículo
BEAM = 10
MAX_SIZE = 5
ANY = "*"

Predicate = tuple[str, str]  # (tipo de granada o ANY, id del callout)


def round_predicates(map_id: str, tokens) -> set[Predicate]:
    out: set[Predicate] = set()
    for t in tokens:
        zone = token_zone(map_id, t[4] * 1024.0, t[5] * 1024.0, t[7])
        if zone is None:
            continue
        out.add((_UTILS[int(np.argmax(t[: len(_UTILS)]))], zone.id))
        out.add((ANY, zone.id))
    return out


def wilson_lower(k: int, n: int, z: float = Z_ONE_SIDED) -> float:
    if n == 0:
        return 0.0
    p = k / n
    centre = p + z * z / (2 * n)
    spread = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return float((centre - spread) / (1 + z * z / n))


@dataclass
class Pool:
    """Rondas de un mapa: qué condiciones cumple cada una y qué site predice el modelo."""

    vocab: dict[Predicate, int]
    has: np.ndarray  # (rondas, condiciones) bool
    pred: np.ndarray  # (rondas,) 0 = A, 1 = B

    @classmethod
    def build(cls, predicates: list[set[Predicate]], pred) -> Pool:
        vocab = {p: j for j, p in enumerate(sorted(set().union(*predicates)))}
        has = np.zeros((len(predicates), len(vocab)), dtype=bool)
        for i, ps in enumerate(predicates):
            has[i, [vocab[p] for p in ps]] = True
        return cls(vocab, has, np.asarray(pred, dtype=int))

    def rows(self, anchor: tuple[Predicate, ...]) -> np.ndarray:
        if any(p not in self.vocab for p in anchor):
            return np.zeros(len(self.pred), dtype=bool)
        return self.has[:, [self.vocab[p] for p in anchor]].all(axis=1)


@dataclass
class Anchor:
    predicates: tuple[Predicate, ...]
    precision: float
    lower: float
    coverage: float
    n: int
    valid: bool


def _measure(pool: Pool, anchor: tuple[Predicate, ...], target: int) -> Anchor:
    rows = pool.rows(anchor)
    n = int(rows.sum())
    k = int((pool.pred[rows] == target).sum())
    return Anchor(anchor, k / n if n else 0.0, wilson_lower(k, n), n / len(pool.pred), n, False)


def _redundant(anchor: tuple[Predicate, ...], p: Predicate) -> bool:
    """"utility en X" junto a "<tipo> en X" no añade nada: una implica la otra."""
    return any(q[1] == p[1] and ANY in (q[0], p[0]) for q in anchor)


def find_anchor(
    pool: Pool,
    candidates: set[Predicate],
    target: int,
    tau: float = TAU,
    beam: int = BEAM,
    max_size: int = MAX_SIZE,
) -> Anchor | None:
    """La regla de más cobertura en ``pool`` con cota inferior de precisión ≥ ``tau``. Si
    ninguna llega, la de mejor cota, con ``valid=False``."""
    cands = sorted(p for p in candidates if p in pool.vocab)
    best: Anchor | None = None
    frontier: list[tuple[Predicate, ...]] = [()]
    for _ in range(max_size):
        seen: set[tuple[Predicate, ...]] = set()
        scored: list[Anchor] = []
        for a in frontier:
            for p in cands:
                if _redundant(a, p):
                    continue
                key = tuple(sorted((*a, p)))
                if key in seen:
                    continue
                seen.add(key)
                m = _measure(pool, key, target)
                if m.n:
                    scored.append(m)
        if not scored:
            break
        valid = [m for m in scored if m.lower >= tau]
        if valid:
            out = max(valid, key=lambda m: (m.coverage, m.lower))
            out.valid = True
            return out
        scored.sort(key=lambda m: (m.lower, m.coverage), reverse=True)
        if best is None or scored[0].lower > best.lower:
            best = scored[0]
        frontier = [m.predicates for m in scored[:beam]]
    return best
