"""Tests for the live-stream heartbeat loop."""

from __future__ import annotations

import asyncio

from pyairseekers import AirseekersApiError

from custom_components.airseekers_tron.camera import describe_sdp, keep_alive


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


class TestDescribeSdp:
    def test_summarises_video_codecs_and_candidates(self) -> None:
        sdp = (
            "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=rtpmap:111 opus/48000/2\r\n"
            "m=video 9 UDP/TLS/RTP/SAVPF 103 104\r\na=rtpmap:103 H264/90000\r\na=rtpmap:104 rtx/90000\r\n"
            "a=candidate:0 1 udp 2130706431 18.158.179.211 8000 typ host generation 0\r\n"
        )

        assert (
            describe_sdp(sdp)
            == "video=['H264'] candidates=['udp/18.158.179.211:8000/host']"
        )

    def test_marks_a_trickle_offer(self) -> None:
        assert "none (trickle)" in describe_sdp(
            "v=0\r\nm=video 9 X 96\r\na=rtpmap:96 VP8/90000\r\n"
        )
