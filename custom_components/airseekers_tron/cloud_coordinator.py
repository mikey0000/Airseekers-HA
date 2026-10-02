"""Cloud coordinator: holds the context the write path needs.

Telemetry is read from the local Foxglove bridge. The cloud is polled slowly
for the things commands depend on (online flag, saved tasks, maps, pending
legacy task) and for the config values backing number/switch entities.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyairseekers import AirseekersAuthError, AirseekersCloud, AirseekersError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class CloudData:
    """Snapshot of the cloud-side state used by write entities."""

    device: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    maps: list[dict[str, Any]] = field(default_factory=list)
    task_state: int | None = None
    current_map_id: str | None = None
    has_legacy_task: bool = False
    legacy_task_id: str = ""

    @property
    def online(self) -> bool:
        return self.device.get("online_status") == 1

    @property
    def volume(self) -> int | None:
        return _int_or_none(self.config.get("SetVolume"))

    @property
    def light_brightness(self) -> int | None:
        return _int_or_none(self.config.get("SetLightBrightness"))

    @property
    def night_mode_raw(self) -> str:
        # Empty SetDarkMode means night mode is off
        return (self.config.get("SetDarkMode") or "").strip()

    @property
    def cut_height(self) -> int | None:
        units = (self.tasks[0].get("task_units") or []) if self.tasks else []
        return units[0].get("cutter_height") if units else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


class AirseekersCloudCoordinator(DataUpdateCoordinator[CloudData]):
    """Poll the Airseekers cloud for write-path context."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: AirseekersCloud,
        sn: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_cloud_{sn}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.sn = sn

    async def _async_update_data(self) -> CloudData:
        try:
            devices, full_status, config, tasks, maps = await asyncio.gather(
                self.api.get_devices(),
                self.api.get_full_status(self.sn),
                self.api.get_device_config(self.sn),
                self.api.get_device_tasks(self.sn),
                self.api.get_device_map(self.sn),
            )
        except AirseekersAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AirseekersError as err:
            raise UpdateFailed(f"Error communicating with cloud: {err}") from err

        device = next((d for d in devices if d.get("sn") == self.sn), None)
        if device is None:
            raise UpdateFailed(f"Device {self.sn} not found in cloud account")

        task_status = full_status.get("task_status") or {}
        return CloudData(
            device=device,
            config=config,
            tasks=tasks,
            maps=maps,
            task_state=task_status.get("state"),
            current_map_id=task_status.get("map_id"),
            has_legacy_task=bool(task_status.get("is_has_legacy_task")),
            legacy_task_id=task_status.get("legacy_task_id") or "",
        )

    async def async_command(self, command: Awaitable[None]) -> None:
        """Run a cloud command, surface its failure, then refresh cloud context."""
        try:
            await command
        except AirseekersAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"Airseekers login rejected: {err}") from err
        except AirseekersError as err:
            raise HomeAssistantError(
                f"Airseekers cloud rejected the command: {err}"
            ) from err
        await self.async_request_refresh()

    async def async_start_mowing(self) -> None:
        """Start mowing using the best available task definition.

        Resolution order:
        1. Pending legacy task (robot docked mid-task to charge). Plain
           /task/resume silently no-ops for these; /task/start with the
           legacy task id continues where it left off.
        2. First scheduled task saved in the app.
        3. The most recently executed task (app Quick Mow), so no
           placeholder schedule is required.
        """
        # Legacy state changes when the robot docks, so don't trust a
        # snapshot that may be minutes old.
        await self.async_refresh()
        data = self.data
        base = data.tasks[0] if data.tasks else {}

        if data.has_legacy_task and data.legacy_task_id:
            _LOGGER.info("Continuing legacy task %s", data.legacy_task_id)
            await self.async_command(
                self.api.start_task(
                    self.sn,
                    task_id=data.legacy_task_id,
                    map_id=data.current_map_id or base.get("map_id"),
                    mode=base.get("mode", 1),
                    task_units=base.get("task_units"),
                )
            )
            return

        if not base:
            try:
                base = await self.api.get_latest_task(self.sn)
            except AirseekersError as err:
                raise HomeAssistantError(f"Cannot read the latest task: {err}") from err
        task = base
        if not task.get("task_units"):
            raise HomeAssistantError(
                "No scheduled or recent task found; run the mower once from "
                "the Airseekers app first"
            )
        await self.async_command(
            self.api.start_task(
                self.sn,
                task_id=task.get("id") or task.get("task_id"),
                map_id=task.get("map_id"),
                mode=task.get("mode", 1),
                task_units=task.get("task_units"),
            )
        )

    async def async_resume(self) -> None:
        """Resume a paused task, or continue a legacy one after a dock cycle."""
        await self.async_refresh()
        # Cloud task_status.state 2 == paused
        data = self.data
        if data.has_legacy_task and data.legacy_task_id and data.task_state != 2:
            await self.async_start_mowing()
            return
        await self.async_command(self.api.resume_task(self.sn))
