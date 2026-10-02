"""Tests for the debounced entity refresh and debug-log redaction."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from custom_components.airseekers_tron import coordinator as coordinator_module
from custom_components.airseekers_tron.coordinator import AirseekersTronCoordinator
from custom_components.airseekers_tron.models import MowerData


class FakeCoordinator(AirseekersTronCoordinator):
    """The real push logic, without Home Assistant around it."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.hass = SimpleNamespace(loop=loop)
        self.data = MowerData()
        self._logged_topics = set()
        self._push_handle = None
        self._last_urgent = None
        self.pushes = 0

    def async_set_updated_data(self, data: MowerData) -> None:
        self.pushes += 1


def battery(level: float) -> SimpleNamespace:
    return SimpleNamespace(
        percentage=level,
        voltage=None,
        current=None,
        temperature=None,
        power_supply_status=None,
    )


def status(*, cutting: bool) -> SimpleNamespace:
    return SimpleNamespace(is_cutting=cutting)


def run(scenario) -> FakeCoordinator:
    async def main() -> FakeCoordinator:
        coord = FakeCoordinator(asyncio.get_running_loop())
        await scenario(coord)
        if coord._push_handle is not None:
            coord._push_handle.cancel()
        return coord

    return asyncio.run(main())


class TestPush:
    def test_a_burst_of_telemetry_is_coalesced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(coordinator_module, "PUSH_INTERVAL_S", 0.05)

        async def scenario(coord: FakeCoordinator) -> None:
            for i in range(200):
                await coord._on_message(
                    "/battery", "sensor_msgs/BatteryState", battery(0.5 + i / 1000)
                )
            pushes_during_burst = coord.pushes
            done = asyncio.Event()
            coord.hass.loop.call_later(0.2, done.set)
            await asyncio.wait_for(done.wait(), timeout=2)
            coord.pushes_during_burst = pushes_during_burst

        coord = run(scenario)

        # The first message pushes (urgent fields go from unknown to known); the rest wait
        assert coord.pushes_during_burst == 1
        assert coord.pushes == 2
        assert coord.data.battery_level == 69.9

    def test_an_urgent_change_is_pushed_at_once(self) -> None:
        async def scenario(coord: FakeCoordinator) -> None:
            await coord._on_message(
                "/battery", "sensor_msgs/BatteryState", battery(0.5)
            )
            before = coord.pushes
            coord.data.is_cutting = True
            coord._push()
            coord.pushes_after_change = coord.pushes - before

        coord = run(scenario)

        assert coord.pushes_after_change == 1

    def test_unchanged_urgent_fields_do_not_push_immediately(self) -> None:
        async def scenario(coord: FakeCoordinator) -> None:
            await coord._on_message(
                "/battery", "sensor_msgs/BatteryState", battery(0.5)
            )
            before = coord.pushes
            await coord._on_message(
                "/battery", "sensor_msgs/BatteryState", battery(0.6)
            )
            coord.pushes_after = coord.pushes - before
            coord.pending = coord._push_handle is not None

        coord = run(scenario)

        assert coord.pushes_after == 0
        assert coord.pending


class TestRedaction:
    def test_network_status_is_not_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret = '{"ssid":"My Street Wifi","iccid":"8932","wifi_ip":"10.0.0.5"}'

        async def scenario(coord: FakeCoordinator) -> None:
            await coord._on_message(
                "/mower_base/net_status",
                "std_msgs/String",
                SimpleNamespace(data=secret),
            )

        with caplog.at_level(logging.DEBUG, logger=coordinator_module.__name__):
            run(scenario)

        assert "My Street Wifi" not in caplog.text
        assert "8932" not in caplog.text
        assert "<redacted>" in caplog.text


class TestShutdown:
    @pytest.mark.regression
    def test_no_reconnect_is_scheduled_while_home_assistant_stops(self) -> None:
        """Killing Home Assistant logged "disconnected, scheduling reconnect" and tried to reconnect."""

        async def scenario(coord: FakeCoordinator) -> None:
            coord.hass.is_stopping = True
            coord._reconnect_task = None
            await coord._on_connection_change(False)

        coord = run(scenario)

        assert coord._reconnect_task is None
        assert coord.pushes == 0

    def test_an_unexpected_drop_schedules_a_reconnect(self) -> None:
        scheduled: list[object] = []

        async def scenario(coord: FakeCoordinator) -> None:
            coord.hass.is_stopping = False
            coord._reconnect_task = None
            coord._schedule_reconnect = lambda: scheduled.append(True)
            await coord._on_connection_change(False)

        run(scenario)

        assert scheduled == [True]
