"""Button platform: cloud commands without a lawn_mower equivalent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cloud_coordinator import AirseekersCloudCoordinator
from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersCloudEntity


@dataclass(frozen=True, kw_only=True)
class AirseekersButtonDescription(ButtonEntityDescription):
    """Describe an Airseekers cloud button."""

    press_fn: Callable[[AirseekersCloudCoordinator], Awaitable[None]]


async def _command(cloud: AirseekersCloudCoordinator, name: str) -> None:
    await cloud.async_command(getattr(cloud.api, name)(cloud.sn))


BUTTONS: tuple[AirseekersButtonDescription, ...] = (
    AirseekersButtonDescription(
        key="stop",
        translation_key="stop",
        icon="mdi:stop",
        press_fn=lambda c: _command(c, "stop_task"),
    ),
    AirseekersButtonDescription(
        key="resume",
        translation_key="resume",
        icon="mdi:play-pause",
        press_fn=lambda c: c.async_resume(),
    ),
    AirseekersButtonDescription(
        key="rtk_reboot",
        translation_key="rtk_reboot",
        icon="mdi:restart",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda c: _command(c, "rtk_reboot"),
    ),
    AirseekersButtonDescription(
        key="clean_warn",
        translation_key="clean_warn",
        icon="mdi:bell-off",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda c: _command(c, "clean_warnings"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(AirseekersButton(entry.runtime_data, desc) for desc in BUTTONS)


class AirseekersButton(AirseekersCloudEntity, ButtonEntity):
    """Button that sends a cloud command."""

    entity_description: AirseekersButtonDescription

    def __init__(
        self, data: AirseekersTronData, description: AirseekersButtonDescription
    ) -> None:
        super().__init__(data, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
