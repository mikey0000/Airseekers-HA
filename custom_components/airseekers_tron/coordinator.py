"""DataUpdateCoordinator for the Airseekers Tron integration."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyairseekers import FoxgloveClient, LocalApi

from .cloud_coordinator import AirseekersCloudCoordinator
from .const import DOMAIN, SUBSCRIBE_TOPICS
from .geo import parse_geojson_zones, resolve_task_areas
from .models import MowerData

_LOGGER = logging.getLogger(__name__)

RECONNECT_INTERVAL = 30
# The bridge publishes hundreds of messages a second; entities are refreshed at
# most this often, except when an _URGENT_FIELDS value changes (D13)
PUSH_INTERVAL_S = 5.0
LORA_NO_LINK_DBM = -128
_URGENT_FIELDS = (
    "mower_work_status",
    "e_stop",
    "lift_triggered",
    "bumper_triggered",
    "rain_triggered",
    "is_charging",
    "is_cutting",
    "task_state",
    "alarm_status",
)
# Topics whose payload identifies the owner's network or SIM; never logged
_PRIVATE_TOPICS = frozenset({"/mower_base/net_status"})


@dataclass
class AirseekersTronData:
    """Runtime data: local push for reads, cloud for writes."""

    local: AirseekersTronCoordinator
    cloud: AirseekersCloudCoordinator
    http: LocalApi
    sn: str


type AirseekersTronConfigEntry = ConfigEntry[AirseekersTronData]


class AirseekersTronCoordinator(DataUpdateCoordinator[MowerData]):
    """Maintain a single Foxglove WS connection and push decoded data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self._entry = entry
        session = async_get_clientsession(hass)
        self.client = FoxgloveClient(
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            session=session,
        )
        self.data = MowerData()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._logged_topics: set[str] = set()
        self._push_handle: asyncio.TimerHandle | None = None
        self._last_urgent: tuple[Any, ...] | None = None

    async def async_setup(self) -> None:
        """Connect to the bridge and start streaming."""
        await self.client.connect()
        await self.client.subscribe(
            SUBSCRIBE_TOPICS,
            message_callback=self._on_message,
            connection_callback=self._on_connection_change,
        )

    async def _on_connection_change(self, connected: bool) -> None:
        if not connected and self.hass.is_stopping:
            # Home Assistant closed the session on shutdown; nothing to reconnect to
            _LOGGER.debug("Foxglove bridge closed during shutdown")
            return
        if not connected:
            _LOGGER.warning("Foxglove bridge disconnected, scheduling reconnect")
            self.async_set_updated_data(self.data)
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self.hass.async_create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        while not self.client.connected and not self.hass.is_stopping:
            await asyncio.sleep(RECONNECT_INTERVAL)
            if self.hass.is_stopping:
                return
            try:
                _LOGGER.debug("Attempting reconnect to Foxglove bridge")
                await self.client.disconnect()
                await self.client.connect()
                await self.client.subscribe(
                    SUBSCRIBE_TOPICS,
                    message_callback=self._on_message,
                    connection_callback=self._on_connection_change,
                )
                _LOGGER.info("Reconnected to Foxglove bridge")
                self.async_set_updated_data(self.data)
                return
            except Exception:
                _LOGGER.debug("Reconnect failed, retrying", exc_info=True)

    async def async_shutdown(self) -> None:
        """Disconnect from the bridge."""
        if self._push_handle is not None:
            self._push_handle.cancel()
            self._push_handle = None
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        await self.client.disconnect()
        await super().async_shutdown()

    async def _async_update_data(self) -> MowerData:
        return self.data

    # ------------------------------------------------------------------
    # Message handlers — one per topic (or group of topics)
    # ------------------------------------------------------------------

    async def _on_message(self, topic: str, schema_name: str, msg: Any) -> None:
        if topic not in self._logged_topics:
            self._logged_topics.add(topic)
            _LOGGER.debug(
                "First message on %s (%s): %s",
                topic,
                schema_name,
                "<redacted>" if topic in _PRIVATE_TOPICS else _msg_to_dict(msg),
            )
        handler = _TOPIC_HANDLERS.get(topic)
        if handler:
            handler(self.data, msg)
            self._push()

    @callback
    def _push(self) -> None:
        """Refresh entities now if an urgent field changed, else within PUSH_INTERVAL_S."""
        urgent = tuple(getattr(self.data, name) for name in _URGENT_FIELDS)
        if urgent != self._last_urgent:
            self._last_urgent = urgent
            self._flush()
        elif self._push_handle is None:
            self._push_handle = self.hass.loop.call_later(PUSH_INTERVAL_S, self._flush)

    @callback
    def _flush(self) -> None:
        if self._push_handle is not None:
            self._push_handle.cancel()
            self._push_handle = None
        self.async_set_updated_data(self.data)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            f = float(value)
            return None if math.isnan(f) or math.isinf(f) else f
        except TypeError, ValueError:
            return None


def _handle_battery(data: MowerData, msg: Any) -> None:
    data.battery_level = AirseekersTronCoordinator._safe_float(
        getattr(msg, "percentage", None)
    )
    if data.battery_level is not None:
        if data.battery_level <= 1.0:
            data.battery_level = round(data.battery_level * 100, 1)
        else:
            data.battery_level = round(data.battery_level, 1)
    raw_voltage = AirseekersTronCoordinator._safe_float(getattr(msg, "voltage", None))
    if raw_voltage is not None and raw_voltage > 100:
        raw_voltage = raw_voltage / 10
    data.battery_voltage = raw_voltage
    data.battery_current = AirseekersTronCoordinator._safe_float(
        getattr(msg, "current", None)
    )
    data.battery_temperature = AirseekersTronCoordinator._safe_float(
        getattr(msg, "temperature", None)
    )
    data.power_supply_status = getattr(msg, "power_supply_status", None)


def _handle_fix(data: MowerData, msg: Any) -> None:
    data.latitude = AirseekersTronCoordinator._safe_float(
        getattr(msg, "latitude", None)
    )
    data.longitude = AirseekersTronCoordinator._safe_float(
        getattr(msg, "longitude", None)
    )
    data.altitude = AirseekersTronCoordinator._safe_float(
        getattr(msg, "altitude", None)
    )
    status = getattr(msg, "status", None)
    if status is not None:
        data.gps_fix_status = getattr(status, "status", None)


_ALARM_SENTINEL = 2**63


def _handle_alarm_status(data: MowerData, msg: Any) -> None:
    val = getattr(msg, "data", None)
    if val is not None and isinstance(val, int) and val >= _ALARM_SENTINEL:
        val = 0
    data.alarm_status = val


_mower_status_fields_logged = False


def _handle_mower_status(data: MowerData, msg: Any) -> None:
    data.mower_status_raw = _msg_to_dict(msg)

    global _mower_status_fields_logged
    if not _mower_status_fields_logged:
        _mower_status_fields_logged = True
        try:
            names = list(getattr(msg, "__dataclass_fields__", {}).keys())
            _LOGGER.debug("mower_base/status schema fields: %s", names)
        except Exception:
            _LOGGER.debug("mower_base/status: cannot read field names")

    data.is_charging = _get_bool(msg, "is_charging")
    data.is_cutting = _get_bool(msg, "is_cutting")
    data.is_moving = _get_bool(msg, "is_moving")
    data.is_docking_done = _get_bool(msg, "is_docking_done")
    data.cmd_moving = _get_bool_multi(msg, "is_cmd_moving", "cmd_moving")
    data.rain_triggered = _get_bool(msg, "rain_triggered")
    data.lift_triggered = _get_bool(msg, "lift_triggered")
    data.bumper_triggered = _get_bool(msg, "bumper_triggered")
    data.e_stop = _get_bool_multi(msg, "stop_triggered", "e_stop")
    data.routing_enabled = _get_bool_multi(
        msg, "bumper_routing_enabled", "routing_enabled"
    )
    brs = getattr(msg, "bumper_routing_status", None)
    if brs is not None:
        data.routing_active = bool(brs)
    else:
        data.routing_active = _get_bool(msg, "routing_active")
    data.battery_gate_open = _get_bool(msg, "battery_gate_open")
    data.mower_work_status = _derive_work_status(data)
    _LOGGER.debug(
        "Mower booleans: cutting=%s moving=%s charging=%s e_stop=%s → status=%s",
        data.is_cutting,
        data.is_moving,
        data.is_charging,
        data.e_stop,
        data.mower_work_status,
    )


def _derive_work_status(data: MowerData) -> int | None:
    """Derive work status from boolean flags + task_info fallback.

    The mower has no mower_work_status field; state is inferred from
    boolean flags with priority: STOPPED > MOWING > MOVING > CHARGING > DOCKED > IDLE.
    If booleans are all false/None but task_info reports "running", use that.
    """
    if data.e_stop:
        return 4
    if data.is_cutting:
        return 1
    if data.is_moving and data.task_state == "running":
        return 1
    if data.is_moving:
        return 3
    if data.is_charging or data.is_docking_done:
        return 5
    if data.task_state == "running":
        return 1
    if data.mower_status_raw:
        return 0
    return None


def _handle_gps_info(data: MowerData, msg: Any) -> None:
    data.gps_info_raw = _msg_to_dict(msg)
    quality = getattr(msg, "quality", None)
    if quality is not None:
        data.num_satellites = getattr(quality, "num_satellites_tracked", None)
        data.gps_quality = AirseekersTronCoordinator._safe_float(
            getattr(quality, "quality", None)
        )
        data.gps_snr = AirseekersTronCoordinator._safe_float(
            getattr(quality, "snr", None)
        )
    else:
        data.num_satellites = getattr(msg, "num_satellites_tracked", None)
        data.gps_quality = AirseekersTronCoordinator._safe_float(
            getattr(msg, "gps_quality", None)
        )
        data.gps_snr = AirseekersTronCoordinator._safe_float(getattr(msg, "snr", None))
    data.nrtk_enabled = _get_bool_multi(msg, "nrtk_enable", "nrtk_enabled")


def _handle_localization_info(data: MowerData, msg: Any) -> None:
    data.localization_raw = _msg_to_dict(msg)
    rtk = getattr(msg, "rtk_status", None)
    if rtk is None:
        rtk = getattr(msg, "fix_type", None)
    data.rtk_fix_type = rtk
    lora = getattr(msg, "lora_rssi_dbm", None)
    if lora is None:
        lora = getattr(msg, "lora_rssi", None)
    rssi = AirseekersTronCoordinator._safe_float(lora)
    # -128 dBm is the radio's "no LoRa link" value (e.g. on NRTK), not a reading
    data.lora_rssi = None if rssi is not None and rssi <= LORA_NO_LINK_DBM else rssi


def _handle_battery_health(data: MowerData, msg: Any) -> None:
    data.battery_health_raw = _msg_to_dict(msg)


def _handle_controller_event(data: MowerData, msg: Any) -> None:
    data.controller_event_raw = _msg_to_dict(msg)


def _handle_notice_code(data: MowerData, msg: Any) -> None:
    data.notice_code_raw = _msg_to_dict(msg)


def _handle_notice_info(data: MowerData, msg: Any) -> None:
    data.notice_info_raw = _msg_to_dict(msg)


def _handle_sensor_info(data: MowerData, msg: Any) -> None:
    data.sensor_info_raw = _msg_to_dict(msg)


def _handle_dev_base_info(data: MowerData, msg: Any) -> None:
    data.dev_base_info_raw = _msg_to_dict(msg)


def _handle_motor_info(data: MowerData, msg: Any) -> None:
    data.motor_info_raw = _msg_to_dict(msg)


def _handle_string_topic(field_name: str):
    def handler(data: MowerData, msg: Any) -> None:
        setattr(data, field_name, getattr(msg, "data", None))

    return handler


def _handle_robot_config(data: MowerData, msg: Any) -> None:
    """The mower's copy of the cloud config keys (SetVolume, SetDarkMode, ...)."""
    raw = getattr(msg, "data", None)
    data.robot_config_raw = raw
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError, TypeError:
        return
    if isinstance(parsed, dict):
        data.robot_config = {str(k): str(v) for k, v in parsed.items()}


def _handle_task_info(data: MowerData, msg: Any) -> None:
    raw = getattr(msg, "data", None)
    data.task_info_raw = raw
    if not raw:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError, TypeError:
        return
    data.task_state = parsed.get("state")
    if "hasLegacyTask" in parsed:
        data.has_legacy_task = bool(parsed["hasLegacyTask"])
        data.legacy_task_id = parsed.get("legacyTaskId") or ""
    if parsed.get("mapId"):
        data.map_id = str(parsed["mapId"])
    data.task_type = parsed.get("type")
    rt = parsed.get("runTime")
    if rt is None:
        rt = parsed.get("run_time")
    if rt is not None:
        data.task_runtime_seconds = _parse_runtime(rt)
    for key in ("topArea", "area_total", "total_area", "area_mowed"):
        val = parsed.get(key)
        if val is not None:
            area = AirseekersTronCoordinator._safe_float(val)
            data.task_area_total = round(area, 1) if area is not None else None
            break
    for key in ("remainingArea", "remaining", "remaining_area", "area_remaining"):
        val = parsed.get(key)
        if val is not None:
            area = AirseekersTronCoordinator._safe_float(val)
            data.task_area_remaining = round(area, 1) if area is not None else None
            break

    raw_params = parsed.get("params")
    if isinstance(raw_params, list):
        data.task_area_ids = [
            str(p.get("areaId", "")) for p in raw_params if p.get("areaId")
        ]
    _resolve_derived_areas(data)


_geojson_join_warned = False


def _handle_geojson_task(data: MowerData, msg: Any) -> None:
    raw = getattr(msg, "geojson", None)
    if not raw:
        return
    zones = parse_geojson_zones(raw)
    if zones:
        data.geojson_zones = zones
        _LOGGER.debug("Parsed %d mowing zones from /geojson_task", len(zones))
        _resolve_derived_areas(data)


def _resolve_derived_areas(data: MowerData) -> None:
    """Recompute mowed/selected/progress from current state.

    Called after either /task_info or /geojson_task updates.
    """
    global _geojson_join_warned

    mowed, selected, zone_remaining, progress = resolve_task_areas(
        zones=data.geojson_zones,
        area_ids=data.task_area_ids,
        top_area=data.task_area_total,
        remaining_area=data.task_area_remaining,
        runtime_seconds=data.task_runtime_seconds,
    )
    data.task_area_mowed = mowed
    data.task_area_selected = selected
    data.task_zone_remaining = zone_remaining
    data.task_progress = progress

    if (
        data.geojson_zones
        and data.task_area_ids
        and selected is None
        and not _geojson_join_warned
    ):
        _geojson_join_warned = True
        _LOGGER.warning(
            "Zone join produced 0 results — areaIds %s did not match "
            "any mowing feature IDs in /geojson_task",
            data.task_area_ids,
        )


def _handle_net_status(data: MowerData, msg: Any) -> None:
    raw = getattr(msg, "data", None)
    data.net_status_raw = raw
    if not raw:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError, TypeError:
        return
    for key in ("wifi_dbm", "wifi_rssi", "rssi", "wifi_signal"):
        val = parsed.get(key)
        if val is not None:
            try:
                data.wifi_rssi = int(val)
            except TypeError, ValueError:
                pass
            break


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_runtime(rt: Any) -> int | None:
    """Parse runtime value — handles HH:MM:SS strings and plain integers."""
    if rt is None or rt == "":
        return None
    if isinstance(rt, str) and ":" in rt:
        parts = rt.split(":")
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError, IndexError:
            return None
    try:
        return int(rt)
    except TypeError, ValueError:
        return None


def _get_bool(msg: Any, attr: str) -> bool | None:
    val = getattr(msg, attr, None)
    if val is None:
        return None
    return bool(val)


def _get_bool_multi(msg: Any, *attrs: str) -> bool | None:
    for attr in attrs:
        val = getattr(msg, attr, None)
        if val is not None:
            return bool(val)
    return None


def _msg_to_dict(msg: Any) -> dict[str, Any]:
    """Best-effort conversion of a rosbags message to a plain dict."""
    if msg is None:
        return {}
    try:
        fields = getattr(msg, "__dataclass_fields__", None)
        if fields:
            return {k: _msg_to_dict(getattr(msg, k)) for k in fields}
    except Exception:
        pass
    if isinstance(msg, bytes):
        return {}
    try:
        return {"value": msg.item() if hasattr(msg, "item") else msg}
    except Exception:
        return {"value": str(msg)}


_TOPIC_HANDLERS: dict[str, Any] = {
    "/battery": _handle_battery,
    "/fix": _handle_fix,
    "/alarm_status": _handle_alarm_status,
    "/mower_base/status": _handle_mower_status,
    "/mower_gps_node/info": _handle_gps_info,
    "/mower_localization_info": _handle_localization_info,
    "/mower_base/battery_health": _handle_battery_health,
    "/controller/event": _handle_controller_event,
    "/notice_code": _handle_notice_code,
    "/notice_info": _handle_notice_info,
    "/mower_sensor_info": _handle_sensor_info,
    "/mower_base/dev_base_info": _handle_dev_base_info,
    "/mower_base/motor_info": _handle_motor_info,
    "/mower_base/net_status": _handle_net_status,
    "/geojson_task": _handle_geojson_task,
    "/task_info": _handle_task_info,
    "/task_report": _handle_string_topic("task_report_raw"),
    "/robot_config": _handle_robot_config,
}
