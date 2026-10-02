"""Switch platform: night mode (cloud config)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersCloudEntity

DEFAULT_NIGHT_MODE = "22:00-06:00"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([AirseekersNightModeSwitch(entry.runtime_data)])


class AirseekersNightModeSwitch(AirseekersCloudEntity, SwitchEntity, RestoreEntity):
    """Night mode, stored as SetDarkMode "HH:MM-HH:MM" (empty = off)."""

    _attr_translation_key = "night_mode"
    _attr_icon = "mdi:weather-night"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, data: AirseekersTronData) -> None:
        super().__init__(data, "night_mode")
        self._last_schedule = data.cloud.data.night_mode_raw or DEFAULT_NIGHT_MODE

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Remember the schedule across turn-off/turn-on and restarts
        if self.coordinator.data.night_mode_raw:
            return
        if (state := await self.async_get_last_state()) is not None:
            self._last_schedule = (
                state.attributes.get("schedule") or self._last_schedule
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        if schedule := self.coordinator.data.night_mode_raw:
            self._last_schedule = schedule
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.night_mode_raw)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"schedule": self._last_schedule}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(
            self.coordinator.api.set_night_mode(
                self.coordinator.sn, self._last_schedule
            )
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(
            self.coordinator.api.set_night_mode(self.coordinator.sn, "")
        )
