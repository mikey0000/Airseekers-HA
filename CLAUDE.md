# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Read `CONSTITUTION.md` first; it is short and binding. Decisions are numbered in
`docs/decisions.md` (cite as D3). Transport rules, API evidence and open questions
live in [pyairseekers](https://github.com/mikey0000/PyAirseekers) (`CONSTITUTION.md`, `docs/`).

## Project overview

Home Assistant (HACS) custom integration for the **Airseekers Tron** robotic mower. Hybrid:

- **Reads** come from the mower's local Foxglove Bridge (`ws://<mower-ip>:8765`, Foxglove WebSocket protocol v1, no auth).
- **Commands** go local first (mower HTTP API on 13344, verified controller stop) with the cloud as fallback (`commands.py`, D15); settings writes, cut height, `start_mowing_advanced` and **live video** go through the Airseekers cloud API.

- **HA domain:** `airseekers_tron`
- **IoT class:** `local_push` (the bridge streams data; the cloud is polled slowly only for write context)
- **Runtime dependency:** [`pyairseekers`](https://github.com/mikey0000/PyAirseekers) (cloud client, Foxglove client, ROS1 deserializer, WHEP helper)

## Safety (critical)

The mower has blades and self-drives. **Read-only telemetry ships first (Phase 1).** Do NOT implement any movement, blade, or dock command until:
1. The `mower_msgs/Trigger` request schema and command codes are read from `advertiseServices` on the physical device.
2. Safe-stop via `/controller/ctrl` is verified on the physical device.

Additional rules:
- Never fire-and-forget a motion command: always confirm the service response (opcode `0x03`)
  or handle `serviceCallFailure`.
- `/cmd_vel` bypasses the mower's control logic (raw teleop, needs a watchdog); `/controller/*` goes through it — prefer `/controller/*` for commands.

Control commands over the **local** bridge are Phase 2 and explicitly gated on on-site verification. Until then the local connection stays strictly read-only; all commands go through the cloud.

## Architecture

```
config_flow        -->  cloud login -> pick mower (by SN) -> local host (prefilled from cloud wifi_ip)
__init__           -->  runtime_data = AirseekersTronData(local, cloud, sn)
coordinator        -->  READ: single persistent Foxglove WS connection (push)
cloud_coordinator  -->  WRITE: AirseekersCloud + slow poll of command context
                        (online, tasks, maps, legacy task, config values)
services           -->  start_mowing_advanced
camera             -->  /api/web/live/open -> WHEP offer to vendor SRS (native HA WebRTC)
```

- Read entities (`sensor`, `binary_sensor`, `device_tracker`, lawn_mower activity) subclass `AirseekersTronEntity` (local coordinator).
- Write entities (`button`, `number`, `switch`, `camera`) subclass `AirseekersCloudEntity` (cloud coordinator).
- Transport code lives in `pyairseekers`; keep protocol/HTTP details there, not here.
- **Message deserialization:** `pyairseekers.local.ros1` registers ROS1 types at runtime from the bridge's advertised schema strings, so vendor `mower_msgs/*` types need no pre-shipped definitions.

## Development commands

```bash
# Install dev dependencies
uv sync

# Run Home Assistant against this checkout (links ../PyAirseekers when present)
scripts/develop

# Run tests
uv run pytest -p no:homeassistant tests

# Run a single test
pytest tests/test_something.py::test_name -v

# Lint / format
ruff check custom_components/ tests/
ruff format custom_components/ tests/

# CI validation (runs automatically on push/PR)
# - hassfest: validates manifest.json against HA requirements
# - HACS action: validates HACS repository structure
```

## Testing approach

- Uses `pytest` + `pytest-homeassistant-custom-component`.
- Transport tests (Foxglove, ROS1, cloud, WHEP) live in `pyairseekers`.
- Run as CI does: `PYTHONPATH=. pytest -p no:homeassistant tests` (the pytest-homeassistant plugin is not needed for these unit tests).
- Test fixtures in `tests/fixtures/` contain topic/service enumerations captured from the real mower.

## Conventions

- Non-trivial changes get the `code-reviewer` agent (`.claude/agents/`) before
  they are reported complete.
- Commits: imperative subject, one change per commit, no attribution trailers.

- Follow Home Assistant integration quality guidelines (config_flow, coordinator, typed entities).
- No blocking I/O in the event loop; everything async.
- Protocol facts (endpoints, topics, services, evidence levels) live in
  pyairseekers' `docs/api/`; decisions for this integration in `docs/decisions.md`.

## Phases

- **Now:** local reads + cloud writes + cloud live video.
- **Later (blocked on on-site verification):** move commands to the local bridge where safe, so the cloud becomes optional.
