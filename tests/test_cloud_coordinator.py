"""Tests for the cloud write path: task resolution and start_mowing_advanced."""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.airseekers_tron.cloud_coordinator import (
    AirseekersCloudCoordinator,
    CloudData,
)
from custom_components.airseekers_tron.services import _start_mowing_advanced

SN = "SN-TEST-0001"
UNIT_A = {"areaId": "a1", "cutter_height": 50, "cut_mode": 1, "cut_speed": 2}
UNIT_B = {"areaId": "b1", "cutter_height": 50, "cut_mode": 1, "cut_speed": 2}
TASK = {"id": "t1", "map_id": "m1", "mode": 0, "task_units": [UNIT_A, UNIT_B]}
MAP = {
    "mapId": "m1",
    "geoData": {
        "features": [
            {"properties": {"type": 1, "name": "A", "id": "a1"}},
            {"properties": {"type": 1, "name": "B", "id": "b1"}},
            {"properties": {"type": 1, "name": "C", "id": "c1"}},
            {"properties": {"type": 6, "name": "dock", "id": "d1"}},
        ]
    },
}


class FakeApi:
    """Records the cloud calls the coordinator makes."""

    def __init__(self, latest: dict[str, Any] | None = None) -> None:
        self.latest = latest or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def start_task(self, sn: str, **kwargs: Any) -> None:
        self.calls.append(("start_task", kwargs))

    async def resume_task(self, sn: str) -> None:
        self.calls.append(("resume_task", {"sn": sn}))

    async def get_latest_task(self, sn: str) -> dict[str, Any]:
        self.calls.append(("get_latest_task", {}))
        return self.latest

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


class FakeCloud(SimpleNamespace):
    """Exposes what the coordinator methods touch, with real awaiting."""

    def __init__(self, data: CloudData, latest: dict[str, Any] | None = None) -> None:
        super().__init__(sn=SN, data=data, api=FakeApi(latest), refreshes=0)

    async def async_refresh(self) -> None:
        self.refreshes += 1

    async def async_command(self, command: Any) -> None:
        await command

    async def async_start_mowing(self) -> None:
        await AirseekersCloudCoordinator.async_start_mowing(self)


def _cloud(data: CloudData, latest: dict[str, Any] | None = None) -> FakeCloud:
    return FakeCloud(data, latest)


def _start_kwargs(cloud: FakeCloud) -> dict[str, Any]:
    starts = [kwargs for name, kwargs in cloud.api.calls if name == "start_task"]
    assert len(starts) == 1, cloud.api.calls
    return starts[0]


class TestStartMowing:
    def test_legacy_task_wins(self) -> None:
        cloud = _cloud(
            CloudData(
                tasks=[TASK],
                current_map_id="m9",
                has_legacy_task=True,
                legacy_task_id="legacy",
            )
        )
        asyncio.run(cloud.async_start_mowing())
        kwargs = _start_kwargs(cloud)
        assert kwargs["task_id"] == "legacy"
        assert kwargs["map_id"] == "m9"
        assert cloud.refreshes >= 1

    def test_scheduled_task(self) -> None:
        cloud = _cloud(CloudData(tasks=[TASK]))
        asyncio.run(cloud.async_start_mowing())
        assert _start_kwargs(cloud)["task_id"] == "t1"
        assert "get_latest_task" not in cloud.api.names()

    def test_falls_back_to_latest_task(self) -> None:
        latest = {"task_id": "", "map_id": "m1", "mode": 1, "task_units": [UNIT_A]}
        cloud = _cloud(CloudData(), latest)
        asyncio.run(cloud.async_start_mowing())
        assert _start_kwargs(cloud)["task_units"] == [UNIT_A]

    def test_no_task_raises(self) -> None:
        cloud = _cloud(CloudData())
        with pytest.raises(HomeAssistantError):
            asyncio.run(cloud.async_start_mowing())
        assert "start_task" not in cloud.api.names()

    def test_resume_paused_uses_resume(self) -> None:
        cloud = _cloud(
            CloudData(
                tasks=[TASK], task_state=2, has_legacy_task=True, legacy_task_id="x"
            )
        )
        asyncio.run(AirseekersCloudCoordinator.async_resume(cloud))
        assert cloud.api.calls == [("resume_task", {"sn": SN})]
        assert "start_task" not in cloud.api.names()

    def test_resume_legacy_restarts_task(self) -> None:
        cloud = _cloud(
            CloudData(
                tasks=[TASK], task_state=0, has_legacy_task=True, legacy_task_id="x"
            )
        )
        asyncio.run(AirseekersCloudCoordinator.async_resume(cloud))
        assert _start_kwargs(cloud)["task_id"] == "x"
        assert "resume_task" not in cloud.api.names()


class TestStartMowingAdvanced:
    def test_no_overrides_keeps_saved_task(self) -> None:
        cloud = _cloud(CloudData(tasks=[TASK], maps=[MAP]))
        asyncio.run(_start_mowing_advanced(cloud, {}))
        kwargs = _start_kwargs(cloud)
        assert kwargs["task_id"] == "t1"
        assert kwargs["task_units"] == [UNIT_A, UNIT_B]

    def test_zone_selection_and_overrides(self) -> None:
        cloud = _cloud(CloudData(tasks=[TASK], maps=[MAP]))
        asyncio.run(
            _start_mowing_advanced(
                cloud,
                {"zones": ["B", "C"], "cut_height": 70, "cut_direction": 90},
            )
        )
        kwargs = _start_kwargs(cloud)
        # Any override makes it an ad-hoc task
        assert kwargs["task_id"] is None
        units = {u["areaId"]: u for u in kwargs["task_units"]}
        # Every zone is sent; unselected ones are skipped and untouched
        assert set(units) == {"a1", "b1", "c1"}
        assert units["a1"] == {**UNIT_A, "cut_mode": 0}
        for aid in ("b1", "c1"):
            assert units[aid]["cut_mode"] == 1
            assert units[aid]["cutter_height"] == 70
            assert units[aid]["path_angle"] == pytest.approx(math.pi / 2)
        # The saved task itself is not mutated
        assert TASK["task_units"] == [UNIT_A, UNIT_B]

    def test_unknown_zone(self) -> None:
        cloud = _cloud(CloudData(tasks=[TASK], maps=[MAP]))
        with pytest.raises(ServiceValidationError):
            asyncio.run(_start_mowing_advanced(cloud, {"zones": ["Z"]}))

    def test_mode_lookup(self) -> None:
        cloud = _cloud(CloudData(tasks=[TASK], maps=[MAP]))
        asyncio.run(_start_mowing_advanced(cloud, {"mode": "edge"}))
        assert _start_kwargs(cloud)["mode"] == 2
