"""Tests for local-first commands with cloud fallback."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.exceptions import HomeAssistantError
from pyairseekers import AirseekersApiError, AirseekersTransportError

from custom_components.airseekers_tron import commands
from custom_components.airseekers_tron.coordinator import (
    _handle_robot_config,
    _handle_task_info,
)
from custom_components.airseekers_tron.models import MowerData
from custom_components.airseekers_tron.number import local_config_int

MAPS = [{"mapId": "24705761407971328", "mapName": "24705761407971328"}]


class FakeHttp:
    """LocalApi stand-in: records calls, raises a queued error per command."""

    def __init__(
        self,
        errors: dict[str, Exception] | None = None,
        maps: list[dict[str, Any]] | None = None,
    ) -> None:
        self.errors = errors or {}
        self.maps = MAPS if maps is None else maps
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _call(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if name in self.errors:
            raise self.errors[name]

    async def map_list(self) -> list[dict[str, Any]]:
        self._call("map_list")
        return self.maps

    async def start_task(self, map_name: str) -> None:
        self._call("start_task", map_name)

    async def pause_task(self) -> None:
        self._call("pause_task")

    async def resume_task(self) -> None:
        self._call("resume_task")

    async def stop_task(self) -> None:
        self._call("stop_task")

    async def dock(self) -> None:
        self._call("dock")


class FakeCloud:
    """Cloud coordinator stand-in recording which commands went through it."""

    sn = "SN-TEST"

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.api = SimpleNamespace(
            pause_task=lambda sn: self._record("pause_task"),
            dock=lambda sn: self._record("dock"),
            stop_task=lambda sn: self._record("stop_task"),
        )

    async def _record(self, name: str) -> None:
        self.sent.append(name)

    async def async_command(self, command: Any) -> None:
        await command

    async def async_start_mowing(self) -> None:
        self.sent.append("start")

    async def async_resume(self) -> None:
        self.sent.append("resume")


class DisconnectedBridge:
    """FoxgloveClient stand-in for a bridge that is not connected."""

    connected = False

    async def service(self, name: str) -> Any:
        raise AirseekersTransportError("Foxglove bridge is not connected")


def mower(http: FakeHttp, *, map_id: str | None = "24705761407971328") -> Any:
    return SimpleNamespace(
        http=http,
        cloud=FakeCloud(),
        local=SimpleNamespace(
            data=MowerData(map_id=map_id), client=DisconnectedBridge()
        ),
    )


UNREACHABLE = AirseekersTransportError("timeout")
REJECTED = AirseekersApiError("no task running", code=501)


class TestLocalFirst:
    @pytest.mark.parametrize(
        ("command", "local_name"),
        [
            ("async_pause", "pause_task"),
            ("async_resume", "resume_task"),
            ("async_dock", "dock"),
        ],
    )
    def test_local_success_does_not_touch_the_cloud(
        self, command: str, local_name: str
    ) -> None:
        data = mower(FakeHttp())

        asyncio.run(getattr(commands, command)(data))

        assert data.http.calls == [(local_name, ())]
        assert data.cloud.sent == []

    def test_start_mows_the_active_map(self) -> None:
        data = mower(FakeHttp())

        asyncio.run(commands.async_start(data))

        assert data.http.calls[-1] == ("start_task", ("24705761407971328",))
        assert data.cloud.sent == []

    @pytest.mark.parametrize(
        ("command", "local_name", "cloud_name"),
        [
            ("async_start", "map_list", "start"),
            ("async_pause", "pause_task", "pause_task"),
            ("async_resume", "resume_task", "resume"),
            ("async_dock", "dock", "dock"),
        ],
    )
    def test_unreachable_mower_falls_back_to_the_cloud(
        self, command: str, local_name: str, cloud_name: str
    ) -> None:
        data = mower(FakeHttp({local_name: UNREACHABLE}))

        asyncio.run(getattr(commands, command)(data))

        assert data.cloud.sent == [cloud_name]

    @pytest.mark.parametrize(
        ("command", "local_name"),
        [("async_pause", "pause_task"), ("async_dock", "dock")],
    )
    def test_a_rejection_from_the_mower_is_not_repeated_through_the_cloud(
        self, command: str, local_name: str
    ) -> None:
        data = mower(FakeHttp({local_name: REJECTED}))

        with pytest.raises(HomeAssistantError, match="no task running"):
            asyncio.run(getattr(commands, command)(data))

        assert data.cloud.sent == []


class TestStop:
    def test_local_http_stop(self) -> None:
        data = mower(FakeHttp())

        asyncio.run(commands.async_stop(data))

        assert data.http.calls == [("stop_task", ())]
        assert data.cloud.sent == []

    @pytest.mark.parametrize("error", [UNREACHABLE, REJECTED])
    def test_every_failure_falls_through_to_the_cloud(self, error: Exception) -> None:
        data = mower(FakeHttp({"stop_task": error}))

        asyncio.run(commands.async_stop(data))

        assert data.cloud.sent == ["stop_task"]


class TestActiveMap:
    def test_no_map_is_a_clear_error(self) -> None:
        with pytest.raises(HomeAssistantError, match="no map"):
            asyncio.run(commands.active_map_name(FakeHttp(maps=[]), None))

    def test_unknown_active_id_with_one_map_uses_it(self) -> None:
        assert (
            asyncio.run(commands.active_map_name(FakeHttp(), "stray-uuid"))
            == "24705761407971328"
        )

    def test_ambiguous_maps_are_refused(self) -> None:
        maps = [{"mapId": "a", "mapName": "A"}, {"mapId": "b", "mapName": "B"}]
        with pytest.raises(HomeAssistantError, match="which map"):
            asyncio.run(commands.active_map_name(FakeHttp(maps=maps), "c"))


class TestLocalReads:
    def test_robot_config_is_parsed(self) -> None:
        data = MowerData()
        raw = json.dumps(
            {"SetVolume": "50", "SetLightBrightness": "100", "SetDarkMode": ""}
        )

        _handle_robot_config(data, SimpleNamespace(data=raw))

        assert local_config_int(data, "SetVolume", None) == 50
        assert local_config_int(data, "Missing", 7) == 7
        assert data.robot_config["SetDarkMode"] == ""

    def test_task_info_legacy_fields_are_parsed(self) -> None:
        data = MowerData()
        raw = json.dumps(
            {
                "hasLegacyTask": True,
                "legacyTaskId": "L1",
                "mapId": "m1",
                "state": "idle",
            }
        )

        _handle_task_info(data, SimpleNamespace(data=raw))

        assert (data.has_legacy_task, data.legacy_task_id, data.map_id) == (
            True,
            "L1",
            "m1",
        )
