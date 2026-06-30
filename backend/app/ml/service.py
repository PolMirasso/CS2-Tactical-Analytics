from __future__ import annotations

import threading

from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.models import User
from app.ml.dataset import build_dataset
from app.ml.model import SitePredictor

_lock = threading.Lock()
_predictor: SitePredictor | None = None
_loaded = False


def _model_path():
    return get_settings().model_dir / "site_predictor.joblib"


def get_predictor() -> SitePredictor:
    """Process-wide predictor; lazily loaded from disk, empty if none trained."""
    global _predictor, _loaded
    with _lock:
        if not _loaded:
            _predictor = _load_from_disk()
            _loaded = True
        return _predictor or SitePredictor()


def _load_from_disk() -> SitePredictor | None:
    import joblib

    path = _model_path()
    if not path.exists():
        return None
    try:
        obj = joblib.load(path)
    except Exception:
        return None
    # Reject a model pickled by an incompatible older version (single-head models
    # lack the two-stage gate/site fields); the caller falls back to the baseline until retrained
    if not isinstance(obj, SitePredictor) or not hasattr(obj, "gate_net"):
        return None
    return obj


def train_model(session: Session, user: User) -> SitePredictor:
    global _predictor, _loaded
    samples, targets, meta = build_dataset(session, user)
    predictor = SitePredictor.train(samples, targets, meta)
    _persist(predictor, samples, targets)
    with _lock:
        _predictor = predictor
        _loaded = True
    return predictor


def _persist(predictor: SitePredictor, samples: list[dict], targets: list[str]) -> None:
    import joblib

    settings = get_settings()
    settings.model_dir.mkdir(parents=True, exist_ok=True)
    if predictor.trained:
        joblib.dump(predictor, _model_path())
    try:
        _export_snapshot(samples, targets)
    except Exception:
        pass


def _export_snapshot(samples: list[dict], targets: list[str]) -> None:
    """Reproducibility: dump the round context table to dataset_dir (best effort)."""
    if not samples:
        return
    import pandas as pd

    settings = get_settings()
    settings.dataset_dir.mkdir(parents=True, exist_ok=True)
    rows = [{**s["context"], "n_tokens": len(s["tokens"])} for s in samples]
    df = pd.DataFrame(rows)
    df["target_site"] = targets
    df.to_parquet(settings.dataset_dir / "rounds.parquet", index=False)
