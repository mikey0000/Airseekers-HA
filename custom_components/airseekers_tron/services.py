"""Services for the Airseekers Tron integration."""

from __future__ import annotations

import logging
import math
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from pyairseekers import AirseekersError
from pyairseekers.const import (
    CUT_SPEED_LOOKUP,
    MAP_FEATURE_KIND_MOWABLE_POLYGON,
    STRATEGY_LOOKUP,
    TASK_MODE_LOOKUP,
    TURNING_MODE_LOOKUP,
)

from .cloud_coordinator import AirseekersCloudCoordinator
from .const import DOMAIN
from .coordinator import AirseekersTronData

_LOGGER = logging.getLogger(__name__)

SERVICE_START_MOWING_ADVANCED = "start_mowing_advanced"

START_MOWING_ADVANCED_SCHEMA = vol.Schema(
    {
        vol.Optional("sn"): cv.string,
        vol.Optional("zones"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("mode"): vol.In(list(TASK_MODE_LOOKUP)),
        # App range is 30-90 mm / -90..90 deg; accept a little wider and let
        # the API reject anything truly invalid.
        vol.Optional("cut_height"): vol.All(int, vol.Range(min=20, max=120)),
        vol.Optional("cut_direction"): vol.All(
            vol.Coerce(float), vol.Range(min=-180, max=359)
        ),
        vol.Optional("cut_speed"): vol.In(list(CUT_SPEED_LOOKUP)),
        vol.Optional("strategy"): vol.In(list(STRATEGY_LOOKUP)),
        vol.Optional("turning_mode"): vol.In(list(TURNING_MODE_LOOKUP)),
    }
)

_UNIT_OVERRIDES = (
    # (service field, task_unit key, converter)
    ("cut_height", "cutter_height", int),
    ("cut_direction", "path_angle", lambda deg: math.radians(float(deg))),
    ("cut_speed", "cut_speed", CUT_SPEED_LOOKUP.__getitem__),
    ("strategy", "strategy", STRATEGY_LOOKUP.__getitem__),
    ("turning_mode", "truning_mode", TURNING_MODE_LOOKUP.__getitem__),
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def start_mowing_advanced(call: ServiceCall) -> None:
        target = call.data.get("sn")
        mowers = [
            entry.runtime_data
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
            and (not target or entry.runtime_data.sn == target)
        ]
        if not mowers:
            raise ServiceValidationError(f"No loaded Airseekers mower {target or ''}")
        for mower in mowers:
            await _start_mowing_advanced(
                mower.cloud, call.data, await _local_maps(mower)
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_MOWING_ADVANCED,
        start_mowing_advanced,
        schema=START_MOWING_ADVANCED_SCHEMA,
    )


async def _local_maps(mower: AirseekersTronData) -> list[dict[str, Any]] | None:
    """The mower's own maps, or None to use the cloud's copy."""
    try:
        return await mower.http.map_list()
    except AirseekersError as err:
        _LOGGER.debug("Local map list unavailable (%s); using the cloud's", err)
        return None


async def _start_mowing_advanced(
    cloud: AirseekersCloudCoordinator,
    options: dict[str, Any],
    maps: list[dict[str, Any]] | None = None,
) -> None:
    """Build a custom task from the first scheduled task and start it.

    Settings not given fall back to that scheduled ("placeholder") task, so
    the user's app-side config wins.
    """
    await cloud.async_refresh()
    data = cloud.data
    if not data.tasks or not data.tasks[0].get("task_units"):
        raise HomeAssistantError(
            "No scheduled task with zones in the Airseekers app; create a "
            "placeholder schedule first"
        )
    maps = maps or data.maps
    if not maps:
        raise HomeAssistantError("No maps loaded for this mower")
    base_task = data.tasks[0]
    base_units: list[dict[str, Any]] = base_task["task_units"]
    current_map = next(
        (m for m in maps if str(m.get("mapId")) == (data.current_map_id or "")), maps[0]
    )

    zone_ids = {
        str(props["name"]): str(props["id"])
        for feat in (current_map.get("geoData") or {}).get("features") or []
        if (props := feat.get("properties") or {}).get("type")
        == MAP_FEATURE_KIND_MOWABLE_POLYGON
        and props.get("name")
    }

    units = [dict(u) for u in base_units]
    if requested := options.get("zones"):
        if missing := [z for z in requested if z not in zone_ids]:
            raise ServiceValidationError(
                f"Unknown zone(s) {missing}; available: {sorted(zone_ids)}"
            )
        selected = {zone_ids[z] for z in requested}
        # The API wants every zone present; cut_mode 1 mows it, 0 skips it
        known = {u.get("areaId") for u in units}
        units += [
            {**base_units[0], "areaId": aid}
            for aid in zone_ids.values()
            if aid not in known
        ]
        for unit in units:
            unit["cut_mode"] = 1 if unit.get("areaId") in selected else 0

    for unit in units:
        if unit.get("cut_mode") == 0:
            continue
        for field, key, convert in _UNIT_OVERRIDES:
            if (value := options.get(field)) is not None:
                unit[key] = convert(value)

    mode = (
        TASK_MODE_LOOKUP[options["mode"]]
        if "mode" in options
        else int(base_task.get("mode") or 0)
    )
    # With any override, omit task_id so the cloud doesn't fall back to the
    # saved task definition (mirrors the app's Quick Mow)
    has_overrides = any(
        options.get(k) is not None
        for k in ("zones", "mode", *(f for f, _, _ in _UNIT_OVERRIDES))
    )
    task_id = None if has_overrides else base_task.get("id") or base_task.get("task_id")
    _LOGGER.debug(
        "start_mowing_advanced: sn=%s task_id=%s mode=%s units=%s",
        cloud.sn,
        task_id,
        mode,
        units,
    )
    await cloud.async_command(
        cloud.api.start_task(
            cloud.sn,
            task_id=task_id,
            map_id=current_map.get("mapId") or base_task.get("map_id"),
            mode=mode,
            task_units=units,
        )
    )
