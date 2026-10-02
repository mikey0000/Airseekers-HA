"""Lawn mower platform: activity from local telemetry, commands via cloud."""

from __future__ import annotations

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import commands
from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersTronEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([AirseekersTronMower(entry.runtime_data)])


class AirseekersTronMower(AirseekersTronEntity, LawnMowerEntity):
    """Lawn mower entity: local activity, cloud commands."""

    _attr_translation_key = "mower"
    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self, data: AirseekersTronData) -> None:
        super().__init__(data)
        self._data = data
        self._attr_unique_id = f"{data.sn}_mower"

    async def async_start_mowing(self) -> None:
        await commands.async_start(self._data)

    async def async_pause(self) -> None:
        await commands.async_pause(self._data)

    async def async_dock(self) -> None:
        await commands.async_dock(self._data)

    @property
    def activity(self) -> LawnMowerActivity | None:
        status = self.coordinator.data.mower_work_status
        if status is None:
            return None
        return _STATUS_MAP.get(status)


_STATUS_MAP: dict[int, LawnMowerActivity] = {
    0: LawnMowerActivity.DOCKED,  # idle
    1: LawnMowerActivity.MOWING,
    2: LawnMowerActivity.PAUSED,
    3: LawnMowerActivity.DOCKED,  # returning to dock
    4: LawnMowerActivity.ERROR,
    5: LawnMowerActivity.DOCKED,  # docked (charging or is_docking_done)
}
