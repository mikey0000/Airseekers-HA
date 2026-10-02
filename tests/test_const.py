"""Tests for topic consistency between const, coordinator, and fixture."""

from __future__ import annotations

from pathlib import Path

from custom_components.airseekers_tron.const import SUBSCRIBE_TOPICS
from custom_components.airseekers_tron.coordinator import _TOPIC_HANDLERS

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "foxglove-topics-core.txt"


def _load_fixture_topics() -> set[str]:
    topics: set[str] = set()
    for line in FIXTURE_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if parts:
            topics.add(parts[0])
    return topics


def _load_fixture_types() -> dict[str, str]:
    types: dict[str, str] = {}
    for line in FIXTURE_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            types[parts[0]] = parts[1]
    return types


class TestTopicConsistency:
    def test_all_handlers_are_subscribed(self) -> None:
        """Every topic in _TOPIC_HANDLERS must be in SUBSCRIBE_TOPICS."""
        handler_topics = set(_TOPIC_HANDLERS.keys())
        subscribe_topics = set(SUBSCRIBE_TOPICS)
        missing = handler_topics - subscribe_topics
        assert not missing, f"Handler topics not in SUBSCRIBE_TOPICS: {missing}"

    def test_all_subscribed_topics_exist_in_fixture(self) -> None:
        """Every topic we subscribe to should exist on the real mower."""
        fixture_topics = _load_fixture_topics()
        subscribe_topics = set(SUBSCRIBE_TOPICS)
        missing = subscribe_topics - fixture_topics
        assert not missing, f"Subscribed topics not in fixture: {missing}"

    def test_handler_count_matches(self) -> None:
        """All subscribed topics should have a handler (no silent drops)."""
        handler_topics = set(_TOPIC_HANDLERS.keys())
        subscribe_topics = set(SUBSCRIBE_TOPICS)
        unhandled = subscribe_topics - handler_topics
        assert not unhandled, f"Subscribed topics with no handler: {unhandled}"

    def test_subscribed_topic_types_match_expected(self) -> None:
        """Pin ROS types for topics whose handlers depend on structure."""
        types = _load_fixture_types()
        assert types["/alarm_status"] == "std_msgs/UInt64"
        assert types["/battery"] == "sensor_msgs/BatteryState"
        assert types["/fix"] == "sensor_msgs/NavSatFix"
        for t in ("/task_info", "/task_report", "/robot_config",
                  "/mower_base/net_status"):
            assert types[t] == "std_msgs/String"
