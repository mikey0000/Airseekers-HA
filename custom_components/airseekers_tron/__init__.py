"""Airseekers Tron integration: local Foxglove reads, cloud writes."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from pyairseekers import AirseekersAuthError, AirseekersCloud, AirseekersError

from .cloud_coordinator import AirseekersCloudCoordinator
from .const import (
    CONF_CLOUD_SCAN_INTERVAL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SERIAL,
    DEFAULT_CLOUD_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import (
    AirseekersTronConfigEntry,
    AirseekersTronCoordinator,
    AirseekersTronData,
)
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: AirseekersTronConfigEntry
) -> bool:
    """Set up Airseekers Tron from a config entry."""
    sn = entry.data[CONF_SERIAL]
    api = AirseekersCloud(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        async_get_clientsession(hass),
    )
    cloud = AirseekersCloudCoordinator(
        hass,
        entry,
        api,
        sn,
        entry.options.get(CONF_CLOUD_SCAN_INTERVAL, DEFAULT_CLOUD_SCAN_INTERVAL),
    )
    # Local first: a retry while the mower is unreachable then costs no cloud login
    local = AirseekersTronCoordinator(hass, entry)
    try:
        await local.async_setup()
    except Exception as err:
        await local.async_shutdown()
        raise ConfigEntryNotReady(
            f"Cannot connect to Foxglove bridge: {err!r}"
        ) from err

    try:
        await api.login()
        await cloud.async_config_entry_first_refresh()
    except AirseekersAuthError as err:
        await local.async_shutdown()
        raise ConfigEntryAuthFailed(str(err)) from err
    except AirseekersError as err:
        await local.async_shutdown()
        raise ConfigEntryNotReady(f"Cannot reach Airseekers cloud: {err}") from err
    except ConfigEntryAuthFailed, ConfigEntryNotReady:
        await local.async_shutdown()
        raise

    entry.runtime_data = AirseekersTronData(local=local, cloud=cloud, sn=sn)
    entry.async_on_unload(local.async_shutdown)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AirseekersTronConfigEntry
) -> bool:
    """Unload an Airseekers Tron config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
