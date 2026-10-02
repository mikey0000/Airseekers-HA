"""Number platform: cloud-stored settings."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cloud_coordinator import AirseekersCloudCoordinator, CloudData
from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersCloudEntity
from .models import MowerData


async def _set_cut_height(cloud: AirseekersCloudCoordinator, value: int) -> None:
    # Saved on the first scheduled task; used by the next start
    if not cloud.data.tasks:
        raise HomeAssistantError(
            "No scheduled task in the Airseekers app to store the cut height on"
        )
    await cloud.api.update_task_cut_height(cloud.data.tasks[0], value)


def local_config_int(local: MowerData, key: str, fallback: int | None) -> int | None:
    """Read a setting from the mower's /robot_config, else the cloud value."""
    try:
        return int(local.robot_config[key])
    except KeyError, ValueError:
        return fallback


@dataclass(frozen=True, kw_only=True)
class AirseekersNumberDescription(NumberEntityDescription):
    """Describe an Airseekers cloud number."""

    value_fn: Callable[[MowerData, CloudData], int | None]
    reads_local: bool = False
    set_fn: Callable[[AirseekersCloudCoordinator, int], Awaitable[None]]


NUMBERS: tuple[AirseekersNumberDescription, ...] = (
    AirseekersNumberDescription(
        key="volume",
        translation_key="volume",
        icon="mdi:volume-high",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda local, cloud: local_config_int(
            local, "SetVolume", cloud.volume
        ),
        reads_local=True,
        set_fn=lambda c, v: c.api.set_volume(c.sn, v),
    ),
    AirseekersNumberDescription(
        key="light_brightness",
        translation_key="light_brightness",
        icon="mdi:brightness-6",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda local, cloud: local_config_int(
            local, "SetLightBrightness", cloud.light_brightness
        ),
        reads_local=True,
        set_fn=lambda c, v: c.api.set_light_brightness(c.sn, v),
    ),
    AirseekersNumberDescription(
        key="cut_height",
        translation_key="cut_height",
        icon="mdi:grass",
        # Range and step of the app's slider
        native_min_value=30,
        native_max_value=90,
        native_step=10,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        value_fn=lambda local, cloud: cloud.cut_height,
        set_fn=_set_cut_height,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(AirseekersNumber(entry.runtime_data, desc) for desc in NUMBERS)


class AirseekersNumber(AirseekersCloudEntity, NumberEntity):
    """Number backed by a cloud setting."""

    entity_description: AirseekersNumberDescription
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, data: AirseekersTronData, description: AirseekersNumberDescription
    ) -> None:
        super().__init__(data, description.key)
        self.entity_description = description
        self._reads_local = description.reads_local

    @property
    def native_value(self) -> int | None:
        return self.entity_description.value_fn(self._local.data, self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(
            self.entity_description.set_fn(self.coordinator, int(value))
        )
