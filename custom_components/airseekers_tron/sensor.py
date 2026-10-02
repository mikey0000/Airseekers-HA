"""Sensor platform for the Airseekers Tron integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersTronEntity
from .models import MowerData

_RTK_FIX_MAP: dict[int, str] = {
    0: "no_fix",
    1: "single",
    2: "float",
    4: "fixed",
    5: "fixed",
}

_RTK_FIX_STRING_MAP: dict[str, str] = {
    "NARROW_INT": "fixed",
    "NARROW_FLOAT": "float",
    "WIDE_INT": "fixed",
    "WIDE_FLOAT": "float",
    "DGPS": "float",
    "SINGLE": "single",
}


def _rtk_fix_value(data: MowerData) -> str | None:
    if data.rtk_fix_type is None:
        return None
    if isinstance(data.rtk_fix_type, str):
        return _RTK_FIX_STRING_MAP.get(data.rtk_fix_type.upper())
    return _RTK_FIX_MAP.get(data.rtk_fix_type)


_WORK_STATUS_MAP: dict[int, str] = {
    0: "idle",
    1: "mowing",
    2: "paused",
    3: "returning",
    4: "error",
    5: "docked",
}

_POWER_SUPPLY_MAP: dict[int, str] = {
    0: "unknown",
    1: "charging",
    2: "discharging",
    3: "not_charging",
    4: "full",
}


def _task_zone_attrs(data: MowerData) -> dict[str, Any]:
    if not data.task_area_ids or not data.geojson_zones:
        return {}
    zones = []
    for aid in data.task_area_ids:
        zone = data.geojson_zones.get(aid)
        if zone is not None:
            zones.append({"name": zone.name or aid, "net_area_m2": zone.net_area})
    return {"zones": zones} if zones else {}


@dataclass(frozen=True, kw_only=True)
class AirseekersTronSensorDescription(SensorEntityDescription):
    """Describe an Airseekers Tron sensor."""

    value_fn: Callable[[MowerData], Any]
    attrs_fn: Callable[[MowerData], dict[str, Any]] | None = None


SENSORS: tuple[AirseekersTronSensorDescription, ...] = (
    AirseekersTronSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_level,
    ),
    AirseekersTronSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.battery_voltage,
    ),
    AirseekersTronSensorDescription(
        key="battery_current",
        translation_key="battery_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.battery_current,
    ),
    AirseekersTronSensorDescription(
        key="battery_temperature",
        translation_key="battery_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.battery_temperature,
    ),
    AirseekersTronSensorDescription(
        key="satellites",
        translation_key="satellites",
        icon="mdi:satellite-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.num_satellites,
    ),
    AirseekersTronSensorDescription(
        key="lora_rssi",
        translation_key="lora_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.lora_rssi,
    ),
    AirseekersTronSensorDescription(
        key="alarm_status",
        translation_key="alarm_status",
        device_class=SensorDeviceClass.ENUM,
        options=["ok", "alarm"],
        icon="mdi:alarm-light",
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            "alarm"
            if d.alarm_status is not None and d.alarm_status != 0
            else "ok"
            if d.alarm_status is not None
            else None
        ),
        attrs_fn=lambda d: (
            {"alarm_code": d.alarm_status}
            if d.alarm_status is not None and d.alarm_status != 0
            else {}
        ),
    ),
    AirseekersTronSensorDescription(
        key="rtk_fix_type",
        translation_key="rtk_fix_type",
        device_class=SensorDeviceClass.ENUM,
        options=["no_fix", "single", "float", "fixed"],
        icon="mdi:crosshairs-gps",
        value_fn=_rtk_fix_value,
    ),
    AirseekersTronSensorDescription(
        key="mower_state",
        translation_key="mower_state",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "mowing", "paused", "returning", "error", "docked"],
        icon="mdi:robot-mower",
        value_fn=lambda d: (
            _WORK_STATUS_MAP.get(d.mower_work_status)
            if d.mower_work_status is not None
            else None
        ),
    ),
    AirseekersTronSensorDescription(
        key="power_supply_status",
        translation_key="power_supply_status",
        device_class=SensorDeviceClass.ENUM,
        options=["unknown", "charging", "discharging", "not_charging", "full"],
        icon="mdi:battery-sync",
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            _POWER_SUPPLY_MAP.get(d.power_supply_status)
            if d.power_supply_status is not None
            else None
        ),
    ),
    AirseekersTronSensorDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.wifi_rssi,
    ),
    AirseekersTronSensorDescription(
        key="gps_quality",
        translation_key="gps_quality",
        icon="mdi:satellite-variant",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.gps_quality,
    ),
    AirseekersTronSensorDescription(
        key="gps_snr",
        translation_key="gps_snr",
        icon="mdi:signal",
        native_unit_of_measurement="dB-Hz",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.gps_snr,
    ),
    AirseekersTronSensorDescription(
        key="task_state",
        translation_key="task_state",
        icon="mdi:clipboard-text",
        value_fn=lambda d: d.task_state,
    ),
    AirseekersTronSensorDescription(
        key="task_type",
        translation_key="task_type",
        icon="mdi:clipboard-list",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.task_type,
    ),
    AirseekersTronSensorDescription(
        key="task_runtime",
        translation_key="task_runtime",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.task_runtime_seconds,
    ),
    AirseekersTronSensorDescription(
        key="task_area_mowed",
        translation_key="task_area_mowed",
        name="Area mowed",
        icon="mdi:grass",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.task_area_mowed,
    ),
    AirseekersTronSensorDescription(
        key="task_area_selected",
        translation_key="task_area_selected",
        name="Selected zone area",
        icon="mdi:select-group",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.task_area_selected,
        attrs_fn=_task_zone_attrs,
    ),
    AirseekersTronSensorDescription(
        key="task_zone_remaining",
        translation_key="task_zone_remaining",
        name="Area remaining",
        icon="mdi:texture-box",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.task_zone_remaining,
    ),
    AirseekersTronSensorDescription(
        key="task_progress",
        translation_key="task_progress",
        name="Mowing progress",
        icon="mdi:percent-circle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            round(d.task_progress * 100, 1) if d.task_progress is not None else None
        ),
    ),
    AirseekersTronSensorDescription(
        key="task_area_total",
        translation_key="task_area_total",
        icon="mdi:texture-box",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.task_area_total,
    ),
    AirseekersTronSensorDescription(
        key="task_area_remaining",
        translation_key="task_area_remaining",
        icon="mdi:texture-box",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.task_area_remaining,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(AirseekersTronSensor(data, desc) for desc in SENSORS)


class AirseekersTronSensor(AirseekersTronEntity, SensorEntity):
    """Sensor entity for an Airseekers Tron mower."""

    entity_description: AirseekersTronSensorDescription

    def __init__(
        self,
        data: AirseekersTronData,
        description: AirseekersTronSensorDescription,
    ) -> None:
        super().__init__(data)
        self.entity_description = description
        self._attr_unique_id = f"{data.sn}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is not None:
            return self.entity_description.attrs_fn(self.coordinator.data)
        return None
