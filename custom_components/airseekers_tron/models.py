"""Data models for the Airseekers Tron integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .geo import ZoneInfo


@dataclass
class MowerData:
    """Snapshot of all mower telemetry received from the Foxglove bridge."""

    # Battery (from /battery — sensor_msgs/BatteryState)
    battery_level: float | None = None
    battery_voltage: float | None = None
    battery_current: float | None = None
    battery_temperature: float | None = None
    power_supply_status: int | None = None

    # Mower status (from /mower_base/status — mower_msgs/MowerBaseDevStatus)
    mower_status_raw: dict[str, Any] = field(default_factory=dict)
    mower_work_status: int | None = None
    is_charging: bool | None = None
    is_cutting: bool | None = None
    is_moving: bool | None = None
    is_docking_done: bool | None = None
    cmd_moving: bool | None = None
    rain_triggered: bool | None = None
    lift_triggered: bool | None = None
    bumper_triggered: bool | None = None
    e_stop: bool | None = None
    routing_enabled: bool | None = None
    routing_active: bool | None = None
    battery_gate_open: bool | None = None

    # GPS (from /fix — sensor_msgs/NavSatFix)
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    gps_fix_status: int | None = None

    # GPS info (from /mower_gps_node/info — mower_gps_msgs/Info)
    num_satellites: int | None = None
    gps_quality: float | None = None
    gps_snr: float | None = None
    gps_info_raw: dict[str, Any] = field(default_factory=dict)

    # Localization (from /mower_localization_info — mower_msgs/MowerLocalizationInfo)
    rtk_fix_type: int | str | None = None
    lora_rssi: float | None = None
    nrtk_enabled: bool | None = None
    localization_raw: dict[str, Any] = field(default_factory=dict)

    # Battery health (from /mower_base/battery_health)
    battery_health_raw: dict[str, Any] = field(default_factory=dict)

    # Network (from /mower_base/net_status — std_msgs/String, JSON payload)
    net_status_raw: str | None = None
    wifi_rssi: int | None = None

    # Task (from /task_info, /task_report — std_msgs/String, JSON payload)
    task_info_raw: str | None = None
    task_report_raw: str | None = None
    task_state: str | None = None
    has_legacy_task: bool | None = None
    legacy_task_id: str | None = None
    map_id: str | None = None
    task_type: str | None = None
    task_runtime_seconds: int | None = None
    task_area_total: float | None = None
    task_area_remaining: float | None = None
    task_area_ids: list[str] = field(default_factory=list)
    task_area_mowed: float | None = None
    task_area_selected: float | None = None
    task_zone_remaining: float | None = None
    task_progress: float | None = None

    # GeoJSON zones (from /geojson_task — foxglove_msgs/GeoJSON)
    geojson_zones: dict[str, ZoneInfo] = field(default_factory=dict)

    # Controller (from /controller/event — mower_msgs/ControllerEvent)
    controller_event_raw: dict[str, Any] = field(default_factory=dict)

    # Alarm/notice
    alarm_status: int | None = None
    notice_code_raw: dict[str, Any] = field(default_factory=dict)
    notice_info_raw: dict[str, Any] = field(default_factory=dict)

    # Device info (from /mower_sensor_info, /mower_base/dev_base_info)
    sensor_info_raw: dict[str, Any] = field(default_factory=dict)
    dev_base_info_raw: dict[str, Any] = field(default_factory=dict)

    # Motor info (from /mower_base/motor_info)
    motor_info_raw: dict[str, Any] = field(default_factory=dict)

    # Config (from /robot_config — std_msgs/String)
    robot_config_raw: str | None = None
    robot_config: dict[str, str] = field(default_factory=dict)
