"""Device tracker platform for the Airseekers Tron integration."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersTronEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([AirseekersTronTracker(entry.runtime_data)])


class AirseekersTronTracker(AirseekersTronEntity, TrackerEntity):
    """GPS device tracker for the Airseekers Tron mower."""

    _attr_translation_key = "position"
    _attr_icon = "mdi:robot-mower"

    def __init__(self, data: AirseekersTronData) -> None:
        super().__init__(data)
        self._attr_unique_id = f"{data.sn}_position"

    @property
    def latitude(self) -> float | None:
        return self.coordinator.data.latitude

    @property
    def longitude(self) -> float | None:
        return self.coordinator.data.longitude

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS
