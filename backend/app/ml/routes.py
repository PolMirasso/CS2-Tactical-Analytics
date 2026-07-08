from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.analytics import aggregate
from app.auth.deps import get_current_user
from app.db import get_session
from app.domain.models import User
from app.domain.schemas import (
    ModelStatusOut,
    PerMapMetric,
    PredictIn,
    PredictOut,
    ReliabilityBin,
    SiteProb,
    TendenciesOut,
)
from app.ml import service
from app.ml.features import SITES
from app.ml.model import SitePredictor

router = APIRouter(prefix="/scouting", tags=["scouting"])


def _status(p: SitePredictor) -> ModelStatusOut:
    bins = getattr(p, "reliability", None) or None
    per_map = getattr(p, "per_map", None) or None
    return ModelStatusOut(
        trained=p.trained,
        trained_at=p.trained_at,
        n_rounds=p.n_rounds,
        n_teams=p.n_teams,
        classes=p.classes,
        accuracy=p.accuracy,
        site_accuracy=getattr(p, "site_accuracy", None),
        baseline_accuracy=p.baseline_accuracy,
        ece=getattr(p, "ece", None),
        ece_uncalibrated=getattr(p, "ece_uncalibrated", None),
        reliability=[ReliabilityBin(**b) for b in bins] if bins else None,
        per_map=[PerMapMetric(**m) for m in per_map] if per_map else None,
        params=getattr(p, "params", None) or None,
    )


def _baseline_dist(session: Session, user: User, map_id: str, team: str | None) -> dict[str, float]:
    dist = aggregate.site_distribution(session, user, map_id=map_id, team=team)
    if dist.total_rounds == 0:
        return {s: 1.0 / len(SITES) for s in SITES}
    return {s.site: s.pct for s in dist.sites}


@router.get("/model", response_model=ModelStatusOut)
def model_status() -> ModelStatusOut:
    return _status(service.get_predictor())


@router.post("/train", response_model=ModelStatusOut)
def train(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ModelStatusOut:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can train the model")
    return _status(service.train_model(session, user))


@router.post("/predict", response_model=PredictOut)
def predict(
    payload: PredictIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PredictOut:
    predictor = service.get_predictor()
    baseline = _baseline_dist(session, user, payload.map_id, payload.team)
    probs = predictor.model_proba(
        map_id=payload.map_id,
        team=payload.team,
        opponent=payload.opponent,
        buy_type=payload.buy_type,
        equip_value=payload.equip_value,
        utility=payload.utility,
    )
    source = "model" if probs is not None else "baseline"
    dist = probs if probs is not None else baseline

    sites = [SiteProb(site=s, prob=dist.get(s, 0.0)) for s in SITES]
    top = max(sites, key=lambda s: s.prob)
    return PredictOut(
        map_id=payload.map_id,
        team=payload.team,
        predicted_site=top.site,
        confidence=top.prob,
        source=source,
        sites=sites,
        baseline=[SiteProb(site=s, prob=baseline.get(s, 0.0)) for s in SITES],
    )


@router.get("/tendencies", response_model=TendenciesOut)
def tendencies(
    map_id: str,
    team: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TendenciesOut:
    dist = aggregate.site_distribution(session, user, map_id=map_id, team=team)
    heatmap = aggregate.utility_heatmap(session, user, map_id=map_id, team=team)
    return TendenciesOut(
        map_id=map_id,
        team=team,
        total_rounds=dist.total_rounds,
        sites=dist.sites,
        heatmap=heatmap,
    )
