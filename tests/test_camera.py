"""Tests for the live-stream heartbeat loop."""

from __future__ import annotations

import asyncio

from pyairseekers import AirseekersApiError

from custom_components.airseekers_tron.camera import keep_alive


class FakeClock:
    """Records sleeps; each sleep lets the loop run one more beat."""

    def __init__(self, beats: int) -> None:
        self.sleeps: list[float] = []
        self.remaining = beats

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if self.remaining == 0:
            raise asyncio.CancelledError
        self.remaining -= 1


def _run(clock: FakeClock, beat) -> None:
    try:
        asyncio.run(keep_alive(beat, interval=10, sleep=clock.sleep))
    except asyncio.CancelledError:
        pass


class TestKeepAlive:
    def test_beats_after_each_interval_until_cancelled(self) -> None:
        clock = FakeClock(beats=3)
        beats: list[int] = []

        async def beat() -> None:
            beats.append(1)

        _run(clock, beat)

        assert len(beats) == 3
        assert clock.sleeps == [10, 10, 10, 10]

    def test_a_failed_beat_does_not_stop_the_loop(self) -> None:
        clock = FakeClock(beats=3)
        attempts: list[int] = []

        async def beat() -> None:
            attempts.append(1)
            if len(attempts) == 1:
                raise AirseekersApiError("device offline", code=309)

        _run(clock, beat)

        assert len(attempts) == 3
