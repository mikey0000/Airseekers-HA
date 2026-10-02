"""Binary sensor platform for the Airseekers Tron integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersTronEntity
from .models import MowerData


@dataclass(frozen=True, kw_only=True)
class AirseekersTronBinarySensorDescription(BinarySensorEntityDescription):
    """Describe an Airseekers Tron binary sensor."""

    value_fn: Callable[[MowerData], bool | None]


BINARY_SENSORS: tuple[AirseekersTronBinarySensorDescription, ...] = (
    AirseekersTronBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.is_charging,
    ),
    AirseekersTronBinarySensorDescription(
        key="cutting",
        translation_key="cutting",
        icon="mdi:content-cut",
        value_fn=lambda d: d.is_cutting,
    ),
    AirseekersTronBinarySensorDescription(
        key="moving",
        translation_key="moving",
        icon="mdi:motion",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.is_moving,
    ),
    AirseekersTronBinarySensorDescription(
        key="rain",
        translation_key="rain",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda d: d.rain_triggered,
    ),
    AirseekersTronBinarySensorDescription(
        key="lifted",
        translation_key="lifted",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.lift_triggered,
    ),
    AirseekersTronBinarySensorDescription(
        key="bumper",
        translation_key="bumper",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.bumper_triggered,
    ),
    AirseekersTronBinarySensorDescription(
        key="e_stop",
        translation_key="e_stop",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda d: d.e_stop,
    ),
    AirseekersTronBinarySensorDescription(
        key="routing_active",
        translation_key="routing_active",
        icon="mdi:map-marker-path",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.routing_active,
    ),
    AirseekersTronBinarySensorDescription(
        key="nrtk",
        translation_key="nrtk",
        icon="mdi:access-point-network",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.nrtk_enabled,
    ),
    AirseekersTronBinarySensorDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.alarm_status is not None and d.alarm_status != 0,
    ),
    AirseekersTronBinarySensorDescription(
        key="battery_gate_open",
        translation_key="battery_gate_open",
        device_class=BinarySensorDeviceClass.OPENING,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.battery_gate_open,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(
        AirseekersTronBinarySensor(data, desc) for desc in BINARY_SENSORS
    )


class AirseekersTronBinarySensor(AirseekersTronEntity, BinarySensorEntity):
    """Binary sensor entity for an Airseekers Tron mower."""

    entity_description: AirseekersTronBinarySensorDescription

    def __init__(
        self,
        data: AirseekersTronData,
        description: AirseekersTronBinarySensorDescription,
    ) -> None:
        super().__init__(data)
        self.entity_description = description
        self._attr_unique_id = f"{data.sn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
