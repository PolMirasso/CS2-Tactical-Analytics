from __future__ import annotations

REGULATION_ROUNDS = 24
REGULATION_HALF = 12
PISTOL_ROUNDS = (1, REGULATION_HALF + 1)

PHASES: list[str] = ["pistol", "first_half", "second_half", "overtime"]


def is_pistol_round(round_number: int) -> bool:
    """First round of each regulation half (1, 13); overtime starts with money"""
    if round_number > REGULATION_ROUNDS:
        return False
    return round_number % REGULATION_HALF == 1


def round_phase(round_number: int) -> str:
    """Match phase of a round, derived from its number alone"""
    if is_pistol_round(round_number):
        return "pistol"
    if round_number > REGULATION_ROUNDS:
        return "overtime"
    return "first_half" if round_number <= REGULATION_HALF else "second_half"


def phase_bounds(phase: str) -> tuple[int, int]:
    """Inclusive round-number range of a half, pistol excluded"""
    if phase == "first_half":
        return 2, REGULATION_HALF
    return REGULATION_HALF + 2, REGULATION_ROUNDS
