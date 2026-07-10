from __future__ import annotations

import pytest

from app.domain.enums import UtilityType
from app.parsing.parser import _grenade_type, _resolve_matchup

# Across a full match both clans appear on T and CT (sides swap at the half),
# so the combined vote tally always contains both names.
_BOTH_SIDES = {"Vitality": 24, "G2": 24}


def test_matchup_never_collapses_to_same_team():
    team, opponent = _resolve_matchup(_BOTH_SIDES, team_hint=None)
    assert team and opponent
    assert team != opponent


def test_hint_anchors_team_and_opponent_is_the_other():
    team, opponent = _resolve_matchup(_BOTH_SIDES, team_hint="G2")
    assert team == "G2"
    assert opponent == "Vitality"


def test_hint_matches_case_insensitively_and_partially():
    team, opponent = _resolve_matchup(_BOTH_SIDES, team_hint="vitality esports")
    assert team == "Vitality"
    assert opponent == "G2"


def test_unmatched_hint_falls_back_but_stays_distinct():
    team, opponent = _resolve_matchup(_BOTH_SIDES, team_hint="Some Unknown Org")
    assert team != opponent
    assert {team, opponent} == {"Vitality", "G2"}


def test_single_clan_has_no_opponent():
    team, opponent = _resolve_matchup({"Vitality": 24}, team_hint="Vitality")
    assert team == "Vitality"
    assert opponent is None


def test_no_clans_uses_hint_as_team():
    team, opponent = _resolve_matchup({}, team_hint="Vitality")
    assert team == "Vitality"
    assert opponent is None


# awpy 2.x reports grenades by engine class name, not short tokens.
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("CSmokeGrenadeProjectile", UtilityType.SMOKE),
        ("CSmokeGrenade", UtilityType.SMOKE),
        ("CFlashbangProjectile", UtilityType.FLASH),
        ("CFlashbang", UtilityType.FLASH),
        ("CHEGrenadeProjectile", UtilityType.HE),
        ("CHEGrenade", UtilityType.HE),
        ("CMolotovProjectile", UtilityType.MOLOTOV),
        ("CMolotovGrenade", UtilityType.MOLOTOV),
        ("CIncendiaryGrenade", UtilityType.MOLOTOV),
        ("smoke", UtilityType.SMOKE),  # sample-data short tokens still work
        ("hegrenade", UtilityType.HE),
    ],
)
def test_grenade_type_maps_awpy_class_names(raw, expected):
    assert _grenade_type(raw) == expected


def test_grenade_type_ignores_decoy_and_unknown():
    assert _grenade_type("CDecoyProjectile") is None
    assert _grenade_type(None) is None
    assert _grenade_type("not_a_grenade") is None


def test_is_pistol_round_regulation_halves_only():
    from app.parsing.parser import is_pistol_round

    assert is_pistol_round(1)
    assert is_pistol_round(13)
    # Overtime rounds start with money, never as pistol rounds.
    assert not any(is_pistol_round(n) for n in (2, 12, 24, 25, 28, 31))
