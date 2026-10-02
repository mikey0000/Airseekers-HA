"""Tests for the parked-position deadband."""

from __future__ import annotations

from custom_components.airseekers_tron.device_tracker import distance_m, next_position
from custom_components.airseekers_tron.models import MowerData

HOME = (-38.0024, 176.0)
# ~0.5 m and ~2 m north of HOME
JITTER = (HOME[0] + 0.5 / 111_320, HOME[1])
MOVED = (HOME[0] + 2.0 / 111_320, HOME[1])


def at(pos: tuple[float, float], *, moving: bool = False) -> MowerData:
    return MowerData(latitude=pos[0], longitude=pos[1], is_moving=moving)


class TestNextPosition:
    def test_first_fix_is_published(self) -> None:
        assert next_position(at(HOME), None) == HOME

    def test_parked_jitter_is_ignored(self) -> None:
        assert next_position(at(JITTER), HOME) == HOME

    def test_parked_move_beyond_the_deadband_is_published(self) -> None:
        assert next_position(at(MOVED), HOME) == MOVED

    def test_every_change_is_published_while_moving(self) -> None:
        assert next_position(at(JITTER, moving=True), HOME) == JITTER

    def test_missing_fix_keeps_the_last_position(self) -> None:
        assert next_position(MowerData(), HOME) == HOME

    def test_distance_is_in_metres(self) -> None:
        assert 1.9 < distance_m(*HOME, *MOVED) < 2.1
