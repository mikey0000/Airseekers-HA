"""Device tracker platform for the Airseekers Tron integration."""

from __future__ import annotations

import math

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersTronEntity
from .models import MowerData

# A parked mower's fix wanders ~0.1-0.8 m; ignore that so the recorder isn't
# fed a new position on every refresh (D14)
PARKED_DEADBAND_M = 1.0
_METRES_PER_DEGREE = 111_320.0


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate ground distance; accurate to well under 1 % at garden scale."""
    dy = (lat2 - lat1) * _METRES_PER_DEGREE
    dx = (lon2 - lon1) * _METRES_PER_DEGREE * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def next_position(
    data: MowerData, published: tuple[float, float] | None
) -> tuple[float, float] | None:
    """Return the position to publish: live while moving, deadbanded while parked."""
    if data.latitude is None or data.longitude is None:
        return published
    live = (data.latitude, data.longitude)
    if published is None or data.is_moving or data.is_cutting:
        return live
    if distance_m(*published, *live) > PARKED_DEADBAND_M:
        return live
    return published


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
        self._published: tuple[float, float] | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._published = next_position(self.coordinator.data, self._published)
        super()._handle_coordinator_update()

    @property
    def latitude(self) -> float | None:
        return self._published[0] if self._published else None

    @property
    def longitude(self) -> float | None:
        return self._published[1] if self._published else None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS
