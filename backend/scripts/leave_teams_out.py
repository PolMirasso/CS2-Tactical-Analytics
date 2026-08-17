from __future__ import annotations

import sys

from sqlalchemy import select

from app.db import _ensure, init_db
from app.domain.models import User
from app.ml.dataset import build_dataset
from app.ml.model import MIN_ROUNDS, SitePredictor
from app.ml.validation import DEFAULT_FOLDS, leave_teams_out


def _fmt(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "    —"


def main() -> None:
    n_folds = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FOLDS

    init_db()
    with _ensure()() as session:
        users = list(session.scalars(select(User).order_by(User.id)))
        user = next((u for u in users if u.is_admin), users[0] if users else None)
        if user is None:
            print("No users in the DB — nothing to validate.")
            return
        samples, targets, timing_targets, meta = build_dataset(session, user)

    print(f"user={user.email}  rounds={len(samples)}  teams={meta.get('n_teams')}")
    if len(samples) < MIN_ROUNDS:
        print(f"Not enough rounds ({len(samples)} < {MIN_ROUNDS}) to train.")
        return

    ref = SitePredictor.train(samples, targets, meta, timing_targets)
    print("\nRandom 80/20 holdout (the model card's numbers, teams seen in training)")
    if ref.trained:
        print(
            f"  3-class {_fmt(ref.accuracy)}   site {_fmt(ref.site_accuracy)}"
            f"   baseline {_fmt(ref.baseline_accuracy)}"
        )
    else:
        print("  (not trained — need A, B and NoPlant rounds)")

    cv = leave_teams_out(samples, targets, timing_targets, n_folds=n_folds)
    print(f"\nLeave-teams-out CV ({cv['n_folds']} folds, {cv['n_teams']} teams)")
    hdr = (
        f"{'fold':<6}{'teams':>6}{'train':>7}{'rounds':>8}{'plant':>7}"
        f"{'3-class':>9}{'site':>8}{'baseline':>10}"
    )
    print(hdr)
    print("-" * len(hdr))
    for i, f in enumerate(cv["folds"], 1):
        print(
            f"{i:<6}{f['n_teams']:>6}{f['n_train']:>7}{f['n_rounds']:>8}{f['n_plant']:>7}"
            f"{_fmt(f['accuracy']):>9}{_fmt(f['site_accuracy']):>8}{_fmt(f['baseline_accuracy']):>10}"
        )
    print("-" * len(hdr))
    print(
        f"{'pooled':<6}{cv['n_teams']:>6}{'':>7}{cv['n_rounds']:>8}{cv['n_plant']:>7}"
        f"{_fmt(cv['accuracy']):>9}{_fmt(cv['site_accuracy']):>8}{_fmt(cv['baseline_accuracy']):>10}"
    )
    for s in cv["skipped"]:
        print(f"  skipped fold ({s['n_teams']} teams, {s['n_train']} train rounds): {s['reason']}")

    print(f"\nPer map, pooled over the folds ({cv['n_folds']}×, unseen teams)")
    hdr2 = f"{'map':<14}{'rounds':>8}{'plant':>7}{'3-class':>9}{'site':>8}{'baseline':>10}"
    print(hdr2)
    print("-" * len(hdr2))
    for r in cv["per_map"]:
        print(
            f"{r['map_id']:<14}{r['n_rounds']:>8}{r['n_plant']:>7}"
            f"{_fmt(r['accuracy']):>9}{_fmt(r['site_accuracy']):>8}{_fmt(r['baseline_accuracy']):>10}"
        )

    print(
        "\nRead the 'site' column: close to the 80/20 line ⇒ it generalises to teams it has\n"
        "never seen. Well below ⇒ the 80/20 number was leaning on team identity.\n"
        "Check 'train' first: holding out a team that owns much of the pool also strips the\n"
        "fold of training rounds, so a low score there is not the same finding."
    )


if __name__ == "__main__":
    main()
