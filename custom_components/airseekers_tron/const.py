"""Constants for the Airseekers Tron integration."""

from homeassistant.const import Platform

DOMAIN = "airseekers_tron"
DEFAULT_PORT = 8765

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_SERIAL = "serial"
CONF_CLOUD_SCAN_INTERVAL = "cloud_scan_interval"

# The cloud is only polled for the context that writes need (online flag,
# scheduled tasks, maps, legacy-task id, config-backed values). Live telemetry
# comes from the local Foxglove bridge, so this can be slow.
DEFAULT_CLOUD_SCAN_INTERVAL = 300

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.DEVICE_TRACKER,
    Platform.LAWN_MOWER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


SUBSCRIBE_TOPICS = [
    "/alarm_status",
    "/battery",
    "/controller/event",
    "/fix",
    "/geojson_task",
    "/mower_base/battery_health",
    "/mower_base/dev_base_info",
    "/mower_base/motor_info",
    "/mower_base/net_status",
    "/mower_base/status",
    "/mower_gps_node/info",
    "/mower_localization_info",
    "/mower_sensor_info",
    "/notice_code",
    "/notice_info",
    "/robot_config",
    "/task_info",
    "/task_report",
]
