"""Mower commands: local first, cloud only when the mower is unreachable (D15)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from homeassistant.exceptions import HomeAssistantError
from pyairseekers import (
    AirseekersApiError,
    AirseekersError,
    AirseekersTransportError,
    LocalApi,
    MowerController,
)

from .coordinator import AirseekersTronData

_LOGGER = logging.getLogger(__name__)


async def _local_then_cloud(
    name: str,
    local: Callable[[], Awaitable[object]],
    cloud: Callable[[], Awaitable[None]],
) -> None:
    try:
        await local()
    except AirseekersTransportError as err:
        _LOGGER.warning("Local %s failed (%s); sending it through the cloud", name, err)
        await cloud()
    except AirseekersApiError as err:
        # The mower answered; repeating the command through the cloud could double it
        raise HomeAssistantError(f"Mower rejected {name}: {err}") from err


async def async_start(data: AirseekersTronData) -> None:
    """Start mowing the mower's active map; cloud start if the mower is unreachable."""

    async def local() -> None:
        await data.http.start_task(
            await active_map_name(data.http, data.local.data.map_id)
        )

    await _local_then_cloud("start", local, data.cloud.async_start_mowing)


async def async_pause(data: AirseekersTronData) -> None:
    """Pause the current task."""
    cloud = data.cloud
    await _local_then_cloud(
        "pause",
        data.http.pause_task,
        lambda: cloud.async_command(cloud.api.pause_task(cloud.sn)),
    )


async def async_resume(data: AirseekersTronData) -> None:
    """Resume the paused task."""
    await _local_then_cloud("resume", data.http.resume_task, data.cloud.async_resume)


async def async_dock(data: AirseekersTronData) -> None:
    """Return to the dock."""
    cloud = data.cloud
    await _local_then_cloud(
        "dock", data.http.dock, lambda: cloud.async_command(cloud.api.dock(cloud.sn))
    )


async def async_stop(data: AirseekersTronData) -> None:
    """Stop: HTTP task stop, then the verified controller stop, then the cloud.

    Stopping twice is harmless, so unlike the other commands every failure
    falls through to the next path.
    """
    try:
        await data.http.stop_task()
    except AirseekersError as err:
        _LOGGER.warning("Local task stop failed (%s); trying the controller stop", err)
    else:
        return
    try:
        await MowerController(data.local.client).stop()
    except AirseekersError as err:
        _LOGGER.warning(
            "Controller stop failed (%s); sending stop through the cloud", err
        )
    else:
        return
    cloud = data.cloud
    await cloud.async_command(cloud.api.stop_task(cloud.sn))


async def active_map_name(api: LocalApi, map_id: str | None) -> str:
    """Return the name of the map to mow: the active one, else the only one."""
    maps = await api.map_list()
    if not maps:
        raise HomeAssistantError(
            "The mower has no map yet; create one in the Airseekers app first"
        )
    chosen = next((m for m in maps if map_id and str(m.get("mapId")) == map_id), None)
    if chosen is None and len(maps) == 1:
        chosen = maps[0]
    if chosen is None:
        raise HomeAssistantError(
            "Cannot tell which map is active; choose one in the Airseekers app"
        )
    return str(chosen.get("mapName") or chosen.get("mapId"))
