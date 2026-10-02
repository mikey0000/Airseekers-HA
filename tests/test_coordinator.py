"""Tests for coordinator message handlers."""

from __future__ import annotations

import math
from types import SimpleNamespace

from custom_components.airseekers_tron.coordinator import (
    AirseekersTronCoordinator,
    _handle_alarm_status,
    _handle_battery,
    _handle_fix,
    _handle_gps_info,
    _handle_localization_info,
    _handle_mower_status,
    _handle_net_status,
    _handle_task_info,
    _parse_runtime,
)
from custom_components.airseekers_tron.models import MowerData
from custom_components.airseekers_tron.sensor import _rtk_fix_value

# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_normal_value(self) -> None:
        assert AirseekersTronCoordinator._safe_float(3.14) == 3.14

    def test_integer_value(self) -> None:
        assert AirseekersTronCoordinator._safe_float(42) == 42.0

    def test_nan_returns_none(self) -> None:
        assert AirseekersTronCoordinator._safe_float(float("nan")) is None

    def test_inf_returns_none(self) -> None:
        assert AirseekersTronCoordinator._safe_float(float("inf")) is None

    def test_neg_inf_returns_none(self) -> None:
        assert AirseekersTronCoordinator._safe_float(float("-inf")) is None

    def test_none_returns_none(self) -> None:
        assert AirseekersTronCoordinator._safe_float(None) is None

    def test_non_numeric_string_returns_none(self) -> None:
        assert AirseekersTronCoordinator._safe_float("not_a_number") is None

    def test_numeric_string(self) -> None:
        assert AirseekersTronCoordinator._safe_float("3.14") == 3.14

    def test_zero(self) -> None:
        assert AirseekersTronCoordinator._safe_float(0) == 0.0


# ---------------------------------------------------------------------------
# _handle_battery
# ---------------------------------------------------------------------------


class TestHandleBattery:
    def test_normal_battery(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(
            percentage=0.85,
            voltage=252,
            current=-1.5,
            temperature=35.0,
            power_supply_status=2,
        )
        _handle_battery(data, msg)
        assert data.battery_level == 85.0
        assert data.battery_voltage == 25.2
        assert data.battery_current == -1.5
        assert data.battery_temperature == 35.0
        assert data.power_supply_status == 2

    def test_percentage_already_0_100(self) -> None:
        """Mower may send percentage as 0-100 instead of 0-1."""
        data = MowerData()
        msg = SimpleNamespace(percentage=85.0, voltage=252, current=0.0,
                              temperature=20.0, power_supply_status=0)
        _handle_battery(data, msg)
        assert data.battery_level == 85.0

    def test_percentage_rounding(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(
            percentage=0.333333,
            voltage=250,
            current=0.0,
            temperature=20.0,
            power_supply_status=0,
        )
        _handle_battery(data, msg)
        assert data.battery_level == 33.3

    def test_voltage_low_value_not_divided(self) -> None:
        """Voltage <= 100 is already in volts (e.g. from a different firmware)."""
        data = MowerData()
        msg = SimpleNamespace(percentage=0.5, voltage=25.2, current=0.0,
                              temperature=20.0, power_supply_status=0)
        _handle_battery(data, msg)
        assert data.battery_voltage == 25.2

    def test_nan_voltage(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(
            percentage=0.5,
            voltage=float("nan"),
            current=0.0,
            temperature=20.0,
            power_supply_status=0,
        )
        _handle_battery(data, msg)
        assert data.battery_voltage is None

    def test_missing_fields(self) -> None:
        data = MowerData()
        msg = SimpleNamespace()
        _handle_battery(data, msg)
        assert data.battery_level is None
        assert data.battery_voltage is None
        assert data.power_supply_status is None


# ---------------------------------------------------------------------------
# _handle_fix
# ---------------------------------------------------------------------------


class TestHandleFix:
    def test_normal_fix(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(
            latitude=50.0755,
            longitude=14.4378,
            altitude=235.0,
            status=SimpleNamespace(status=2),
        )
        _handle_fix(data, msg)
        assert abs(data.latitude - 50.0755) < 1e-4
        assert abs(data.longitude - 14.4378) < 1e-4
        assert data.altitude == 235.0
        assert data.gps_fix_status == 2

    def test_no_status_field(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(latitude=50.0, longitude=14.0, altitude=200.0)
        _handle_fix(data, msg)
        assert data.gps_fix_status is None

    def test_nan_coordinates(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(
            latitude=float("nan"),
            longitude=float("inf"),
            altitude=0.0,
        )
        _handle_fix(data, msg)
        assert data.latitude is None
        assert data.longitude is None


# ---------------------------------------------------------------------------
# _handle_alarm_status
# ---------------------------------------------------------------------------


class TestHandleAlarmStatus:
    def test_normal_alarm(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(data=42)
        _handle_alarm_status(data, msg)
        assert data.alarm_status == 42

    def test_zero_alarm(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(data=0)
        _handle_alarm_status(data, msg)
        assert data.alarm_status == 0

    def test_sentinel_near_max_uint64(self) -> None:
        """Values >= 2^63 are treated as 'no alarm' sentinel."""
        data = MowerData()
        msg = SimpleNamespace(data=18446744071562067968)
        _handle_alarm_status(data, msg)
        assert data.alarm_status == 0

    def test_missing_data_field(self) -> None:
        data = MowerData()
        msg = SimpleNamespace()
        _handle_alarm_status(data, msg)
        assert data.alarm_status is None


# ---------------------------------------------------------------------------
# _handle_mower_status
# ---------------------------------------------------------------------------


class TestHandleMowerStatus:
    def test_confirmed_field_names(self) -> None:
        """Use confirmed 🟢 field names."""
        data = MowerData()
        msg = SimpleNamespace(
            is_charging=True,
            is_cutting=False,
            is_moving=True,
            is_docking_done=False,
            is_cmd_moving=False,
            rain_triggered=False,
            lift_triggered=False,
            bumper_triggered=False,
            stop_triggered=False,
            bumper_routing_enabled=True,
            bumper_routing_status=1,
            battery_gate_open=False,
        )
        _handle_mower_status(data, msg)
        assert data.is_charging is True
        assert data.is_cutting is False
        assert data.is_moving is True
        assert data.cmd_moving is False
        assert data.e_stop is False
        assert data.routing_enabled is True
        assert data.routing_active is True
        assert data.mower_work_status == 3  # moving (derived)

    def test_fallback_field_names(self) -> None:
        """Guessed field names still work as fallback."""
        data = MowerData()
        msg = SimpleNamespace(
            cmd_moving=True,
            e_stop=True,
            routing_enabled=False,
            routing_active=False,
        )
        _handle_mower_status(data, msg)
        assert data.cmd_moving is True
        assert data.e_stop is True
        assert data.routing_enabled is False
        assert data.routing_active is False

    def test_bumper_routing_status_zero_is_inactive(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(bumper_routing_status=0)
        _handle_mower_status(data, msg)
        assert data.routing_active is False

    def test_derive_from_booleans_cutting(self) -> None:
        """No mower_work_status field — derive from boolean flags."""
        data = MowerData()
        msg = SimpleNamespace(is_cutting=True, is_moving=True)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 1  # mowing

    def test_derive_from_booleans_stopped(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(stop_triggered=True, is_cutting=True)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 4  # error (stop has priority)

    def test_derive_moving_during_task_is_mowing(self) -> None:
        """Moving without cutting during a running task = repositioning, not returning."""
        data = MowerData()
        data.task_state = "running"
        msg = SimpleNamespace(is_moving=True, is_cutting=False)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 1  # mowing (repositioning between paths)

    def test_derive_moving_no_task_is_returning(self) -> None:
        """Moving without an active task = returning to dock."""
        data = MowerData()
        msg = SimpleNamespace(is_moving=True)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 3  # returning

    def test_derive_from_booleans_charging(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(is_charging=True)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 5  # docked

    def test_derive_from_booleans_docking_done(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(is_docking_done=True)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 5  # docked

    def test_derive_from_booleans_idle(self) -> None:
        """All booleans false — idle on dock."""
        data = MowerData()
        msg = SimpleNamespace(
            is_charging=False, is_cutting=False, is_moving=False,
            stop_triggered=False, is_docking_done=False,
        )
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 0  # idle

    def test_missing_boolean_fields(self) -> None:
        """All booleans missing — still derives idle from having received data."""
        data = MowerData()
        msg = SimpleNamespace()
        _handle_mower_status(data, msg)
        assert data.is_charging is None
        assert data.is_cutting is None
        assert data.mower_work_status == 0  # idle (we received a message)

    def test_task_info_fallback_mowing(self) -> None:
        """If booleans are all None but task_state is running, derive MOWING."""
        data = MowerData()
        data.task_state = "running"
        msg = SimpleNamespace()
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 1  # mowing (from task_state fallback)

    def test_task_info_no_override_charging(self) -> None:
        """is_charging wins over task_state — mower may charge mid-task."""
        data = MowerData()
        data.task_state = "running"
        msg = SimpleNamespace(is_charging=True)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 5  # charging beats task_state

    def test_mower_work_status_field_ignored(self) -> None:
        """mower_work_status in the ROS schema defaults to 0; always derive."""
        data = MowerData()
        msg = SimpleNamespace(mower_work_status=0, is_cutting=True)
        _handle_mower_status(data, msg)
        assert data.mower_work_status == 1  # mowing (from is_cutting, not field)


# ---------------------------------------------------------------------------
# _handle_gps_info
# ---------------------------------------------------------------------------


class TestHandleGpsInfo:
    def test_nested_quality_object(self) -> None:
        """Confirmed schema: quality fields are nested under a quality object."""
        data = MowerData()
        msg = SimpleNamespace(
            quality=SimpleNamespace(
                num_satellites_tracked=12,
                quality=95.5,
                snr=40.0,
            ),
            nrtk_enable=True,
        )
        _handle_gps_info(data, msg)
        assert data.num_satellites == 12
        assert data.gps_quality == 95.5
        assert data.gps_snr == 40.0
        assert data.nrtk_enabled is True

    def test_flat_fallback(self) -> None:
        """Fallback to top-level fields if quality object missing."""
        data = MowerData()
        msg = SimpleNamespace(
            num_satellites_tracked=8,
            gps_quality=80.0,
            snr=30.0,
        )
        _handle_gps_info(data, msg)
        assert data.num_satellites == 8
        assert data.gps_quality == 80.0
        assert data.gps_snr == 30.0

    def test_missing_fields(self) -> None:
        data = MowerData()
        msg = SimpleNamespace()
        _handle_gps_info(data, msg)
        assert data.num_satellites is None
        assert data.gps_quality is None
        assert data.gps_snr is None


# ---------------------------------------------------------------------------
# _handle_localization_info
# ---------------------------------------------------------------------------


class TestHandleLocalizationInfo:
    def test_confirmed_field_names(self) -> None:
        """Confirmed schema: rtk_status is a string, lora_rssi_dbm."""
        data = MowerData()
        msg = SimpleNamespace(
            rtk_status="NARROW_INT", lora_rssi_dbm=-65.0
        )
        _handle_localization_info(data, msg)
        assert data.rtk_fix_type == "NARROW_INT"
        assert data.lora_rssi == -65.0

    def test_fallback_field_names(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(fix_type=4, lora_rssi=-50.0)
        _handle_localization_info(data, msg)
        assert data.rtk_fix_type == 4
        assert data.lora_rssi == -50.0

    def test_missing_fields(self) -> None:
        data = MowerData()
        msg = SimpleNamespace()
        _handle_localization_info(data, msg)
        assert data.rtk_fix_type is None
        assert data.lora_rssi is None

    def test_rtk_string_to_sensor_value(self) -> None:
        """RTK string status maps to HA enum values."""
        data = MowerData()
        data.rtk_fix_type = "NARROW_INT"
        assert _rtk_fix_value(data) == "fixed"
        data.rtk_fix_type = "NARROW_FLOAT"
        assert _rtk_fix_value(data) == "float"
        data.rtk_fix_type = "SINGLE"
        assert _rtk_fix_value(data) == "single"

    def test_rtk_int_to_sensor_value(self) -> None:
        """Integer RTK values still work via fallback map."""
        data = MowerData()
        data.rtk_fix_type = 4
        assert _rtk_fix_value(data) == "fixed"
        data.rtk_fix_type = 0
        assert _rtk_fix_value(data) == "no_fix"


# ---------------------------------------------------------------------------
# _handle_task_info
# ---------------------------------------------------------------------------


class TestHandleTaskInfo:
    def test_confirmed_field_names(self) -> None:
        """Confirmed camelCase fields."""
        data = MowerData()
        payload = '{"state": "running", "type": "auto_mow", "runTime": "01:30:00", "topArea": 500.5678, "remainingArea": 100.1234}'
        msg = SimpleNamespace(data=payload)
        _handle_task_info(data, msg)
        assert data.task_state == "running"
        assert data.task_type == "auto_mow"
        assert data.task_runtime_seconds == 5400
        assert data.task_area_total == 500.6
        assert data.task_area_remaining == 100.1

    def test_runtime_integer_fallback(self) -> None:
        data = MowerData()
        payload = '{"runTime": 120}'
        msg = SimpleNamespace(data=payload)
        _handle_task_info(data, msg)
        assert data.task_runtime_seconds == 120

    def test_snake_case_fallback(self) -> None:
        """Fallback snake_case field names still work."""
        data = MowerData()
        payload = '{"state": "done", "run_time": 60, "area_total": 300.0, "remaining_area": 50.0}'
        msg = SimpleNamespace(data=payload)
        _handle_task_info(data, msg)
        assert data.task_runtime_seconds == 60
        assert data.task_area_total == 300.0
        assert data.task_area_remaining == 50.0

    def test_malformed_json(self) -> None:
        data = MowerData()
        data.task_state = "previous"
        msg = SimpleNamespace(data="{not valid json}")
        _handle_task_info(data, msg)
        assert data.task_state == "previous"

    def test_empty_payload(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(data="")
        _handle_task_info(data, msg)
        assert data.task_state is None

    def test_missing_data_field(self) -> None:
        data = MowerData()
        msg = SimpleNamespace()
        _handle_task_info(data, msg)
        assert data.task_info_raw is None


# ---------------------------------------------------------------------------
# _handle_net_status
# ---------------------------------------------------------------------------


class TestHandleNetStatus:
    def test_wifi_dbm_confirmed(self) -> None:
        """Confirmed field name."""
        data = MowerData()
        payload = '{"wifi_dbm": -80}'
        msg = SimpleNamespace(data=payload)
        _handle_net_status(data, msg)
        assert data.wifi_rssi == -80

    def test_wifi_rssi_fallback(self) -> None:
        data = MowerData()
        payload = '{"wifi_rssi": -45}'
        msg = SimpleNamespace(data=payload)
        _handle_net_status(data, msg)
        assert data.wifi_rssi == -45

    def test_rssi_alias(self) -> None:
        data = MowerData()
        payload = '{"rssi": -50}'
        msg = SimpleNamespace(data=payload)
        _handle_net_status(data, msg)
        assert data.wifi_rssi == -50

    def test_malformed_json(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(data="not json")
        _handle_net_status(data, msg)
        assert data.wifi_rssi is None

    def test_empty_payload(self) -> None:
        data = MowerData()
        msg = SimpleNamespace(data="")
        _handle_net_status(data, msg)
        assert data.wifi_rssi is None


# ---------------------------------------------------------------------------
# _parse_runtime
# ---------------------------------------------------------------------------


class TestParseRuntime:
    def test_hh_mm_ss(self) -> None:
        assert _parse_runtime("01:30:00") == 5400

    def test_zero_time(self) -> None:
        assert _parse_runtime("00:00:00") == 0

    def test_short_time(self) -> None:
        assert _parse_runtime("00:05:30") == 330

    def test_integer(self) -> None:
        assert _parse_runtime(120) == 120

    def test_integer_string(self) -> None:
        assert _parse_runtime("120") == 120

    def test_none(self) -> None:
        assert _parse_runtime(None) is None

    def test_empty_string(self) -> None:
        """runTime is empty string at task start."""
        assert _parse_runtime("") is None

    def test_invalid_string(self) -> None:
        assert _parse_runtime("not_a_time") is None

    def test_partial_time(self) -> None:
        assert _parse_runtime("05:30") is None


class TestLoraNoLink:
    def test_no_link_sentinel_reads_as_unknown(self) -> None:
        data = MowerData()
        _handle_localization_info(data, SimpleNamespace(rtk_status="SINGLE", lora_rssi_dbm=-128))
        assert data.lora_rssi is None

    def test_real_reading_is_kept(self) -> None:
        data = MowerData()
        _handle_localization_info(data, SimpleNamespace(rtk_status="NARROW_INT", lora_rssi_dbm=-87))
        assert data.lora_rssi == -87.0
