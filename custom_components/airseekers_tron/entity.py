"""Base entities for the Airseekers Tron integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cloud_coordinator import AirseekersCloudCoordinator
from .const import DOMAIN
from .coordinator import AirseekersTronCoordinator, AirseekersTronData


def _device_info(sn: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, sn)},
        name="Airseekers Tron",
        manufacturer="Airseekers",
        model="Tron",
        serial_number=sn,
    )


class AirseekersTronEntity(CoordinatorEntity[AirseekersTronCoordinator]):
    """Entity backed by local Foxglove telemetry (read path)."""

    _attr_has_entity_name = True

    def __init__(self, data: AirseekersTronData) -> None:
        super().__init__(data.local)
        self._attr_device_info = _device_info(data.sn)

    @property
    def available(self) -> bool:
        return self.coordinator.client.connected and super().available


class AirseekersCloudEntity(CoordinatorEntity[AirseekersCloudCoordinator]):
    """Entity that writes through the cloud (write path)."""

    _attr_has_entity_name = True

    def __init__(self, data: AirseekersTronData, key: str) -> None:
        super().__init__(data.cloud)
        self._attr_device_info = _device_info(data.sn)
        self._attr_unique_id = f"{data.sn}_{key}"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.online
