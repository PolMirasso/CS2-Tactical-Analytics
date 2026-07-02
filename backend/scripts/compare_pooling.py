"""Compare the three DeepSets poolings on the current dataset (offline).

Trains SitePredictor once per pooling on the SAME 80/20 held-out split (train()
seeds the split with 0), so the rows are a fair head-to-head. Prints 3-class
accuracy, site accuracy (A-vs-B given a plant — the metric that matters to the
tool), baseline, and ECE before→after calibration.
"""
from __future__ import annotations

from sqlalchemy import select

import app.ml.model as M
from app.db import _ensure, init_db
from app.domain.models import User
from app.ml.dataset import build_dataset
from app.ml.deepsets import POOLINGS


def main() -> None:
    init_db()
    with _ensure()() as session:
        users = list(session.scalars(select(User).order_by(User.id)))
        user = next((u for u in users if u.is_admin), users[0] if users else None)
        if user is None:
            print("No users in the DB — nothing to compare.")
            return
        samples, targets, meta = build_dataset(session, user)

    print(f"user={user.email}  rounds={len(samples)}  teams={meta.get('n_teams')}")
    if len(samples) < M.MIN_ROUNDS:
        print(f"Not enough rounds ({len(samples)} < {M.MIN_ROUNDS}) to train.")
        return

    trained = []
    for pooling in POOLINGS:
        M._POOLING = pooling
        trained.append((pooling, M.SitePredictor.train(samples, targets, meta)))

    hdr = (
        f"{'pooling':<10}{'3-class':>9}{'site':>9}{'baseline':>10}"
        f"{'ECE_pre':>9}{'ECE':>8}   T gate/site"
    )
    print("\n" + hdr)
    print("-" * len(hdr))
    for pooling, p in trained:
        if not p.trained:
            print(f"{pooling:<10}  (not trained — need A, B and NoPlant rounds)")
            continue
        print(
            f"{pooling:<10}{p.accuracy:>9.3f}{(p.site_accuracy or 0):>9.3f}"
            f"{p.baseline_accuracy:>10.3f}{p.ece_uncalibrated:>9.3f}{p.ece:>8.3f}"
            f"   {p.params['gate_T']}/{p.params['site_T']}"
        )
    print("\nPick the best 'site' column, set _POOLING in app/ml/model.py, retrain.")


if __name__ == "__main__":
    main()
