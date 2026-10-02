"""Config flow for Airseekers Tron: cloud account, then the local bridge."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)
from pyairseekers import (
    AirseekersAuthError,
    AirseekersCloud,
    AirseekersError,
    FoxgloveClient,
)

from .const import (
    CONF_CLOUD_SCAN_INTERVAL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SERIAL,
    DEFAULT_CLOUD_SCAN_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
)
from .coordinator import AirseekersTronConfigEntry

_LOGGER = logging.getLogger(__name__)

CLOUD_SCHEMA = vol.Schema(
    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
)


async def _cloud_login(
    flow: ConfigFlow, email: str, password: str
) -> tuple[AirseekersCloud | None, str | None]:
    """Log in; return (client, error key)."""
    api = AirseekersCloud(email, password, async_get_clientsession(flow.hass))
    try:
        await api.login()
    except AirseekersAuthError:
        return None, "invalid_auth"
    except AirseekersError:
        return None, "cannot_connect"
    return api, None


class AirseekersTronConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Airseekers Tron."""

    VERSION = 2

    def __init__(self) -> None:
        self._cloud: dict[str, str] = {}
        self._api: AirseekersCloud | None = None
        self._devices: dict[str, dict[str, Any]] = {}
        self._serial: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: AirseekersTronConfigEntry,
    ) -> AirseekersTronOptionsFlow:
        return AirseekersTronOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: cloud account (used for commands and live video)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api, error = await _cloud_login(
                self, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if api is not None:
                try:
                    devices = await api.get_devices()
                except AirseekersError:
                    error = "cannot_connect"
                else:
                    self._devices = {d["sn"]: d for d in devices if d.get("sn")}
                    error = None if self._devices else "no_devices"
            if error:
                errors["base"] = error
            else:
                self._cloud = user_input
                self._api = api
                if len(self._devices) == 1:
                    return await self.async_step_device(
                        {CONF_SERIAL: next(iter(self._devices))}
                    )
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CLOUD_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: pick the mower (skipped with a single device)."""
        if user_input is not None:
            self._serial = user_input[CONF_SERIAL]
            await self.async_set_unique_id(self._serial)
            self._abort_if_unique_id_configured()
            return await self.async_step_local()

        options = [
            SelectOptionDict(value=sn, label=f"{d.get('name') or 'Tron'} ({sn})")
            for sn, d in self._devices.items()
        ]
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERIAL): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: the mower's local Foxglove bridge (used for all reads)."""
        assert self._serial is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            client = FoxgloveClient(
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                session=async_get_clientsession(self.hass),
            )
            try:
                await client.connect()
                await client.disconnect()
            except Exception:
                _LOGGER.debug("Foxglove connection failed", exc_info=True)
                errors["base"] = "cannot_connect_local"
            else:
                return self.async_create_entry(
                    title=f"Airseekers Tron ({self._serial})",
                    data={**self._cloud, CONF_SERIAL: self._serial, **user_input},
                )

        suggested = user_input or {
            CONF_HOST: await self._suggest_host(),
            CONF_PORT: DEFAULT_PORT,
        }
        return self.async_show_form(
            step_id="local",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    }
                ),
                suggested,
            ),
            errors=errors,
        )

    async def _suggest_host(self) -> str | None:
        """Prefill the mower's LAN address as reported by the cloud."""
        if self._api is None or self._serial is None:
            return None
        try:
            status = await self._api.get_full_status(self._serial)
        except AirseekersError:
            return None
        return (status.get("net_info") or {}).get("wifi_ip") or None

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-enter cloud credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            api, error = await _cloud_login(
                self, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if api is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CLOUD_SCHEMA, {CONF_EMAIL: entry.data[CONF_EMAIL]}
            ),
            errors=errors,
        )


class AirseekersTronOptionsFlow(OptionsFlowWithReload):
    """Options: how often the cloud is polled for write context."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CLOUD_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_CLOUD_SCAN_INTERVAL, DEFAULT_CLOUD_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600))
                }
            ),
        )
