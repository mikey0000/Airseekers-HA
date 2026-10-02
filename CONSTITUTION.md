# Constitution

The rules that do not bend for the Airseekers Tron Home Assistant integration.
A change that breaks one needs a new numbered entry in `docs/decisions.md`
that supersedes it. Transport-level rules live in pyairseekers'
`CONSTITUTION.md` and apply here too.

## 1. Local first, cloud as fallback

Telemetry comes only from the local push coordinator (`coordinator.py`) and
is never polled from the cloud. Commands go to the mower locally first and to
the cloud only when the mower is unreachable (`commands.py`, D15). The cloud
coordinator (`cloud_coordinator.py`) is polled slowly, only for what
cloud-only features need (D3).

## 2. Local commands only through pyairseekers' sanctioned paths

Local commands go through `pyairseekers.LocalApi` task commands (pyairseekers
D17) and `MowerController.stop` (pyairseekers D15), and only from
`commands.py`. Nothing here publishes to the Foxglove bridge, calls
`call_service`, or writes maps.

## 3. No transport code here

HTTP, WebSocket, ROS decoding and WHEP live in `pyairseekers`. This package
maps library calls to Home Assistant concepts and nothing else. A missing
endpoint is added to the library first.

## 4. Commands never fail silently

Every command goes through `commands.py` or, for cloud-only features,
`AirseekersCloudCoordinator.async_command`,
which turns a library error into `HomeAssistantError` (and a rejected login
into a reauth flow), then refreshes. No entity swallows a failed command or
logs-and-continues.

## 5. Secrets stay in the config entry

Credentials live only in the config entry. The password, tokens and the live
stream URL never appear in logs, state attributes, diagnostics or exceptions.

## 6. Home Assistant quality

Config flow with reauth and options, `entry.runtime_data`, entity
descriptions, translated names, unique ids and the device keyed by serial
number, `has_entity_name`. Follow the Integration Quality Scale; deviations
are decisions.

## 7. Tests and docs are part of the change

Behaviour changes come with tests (`docs/testing.md` in pyairseekers sets the
style: hand-written fakes over mocks, outcomes over plumbing). Design lives in
`docs/`, comments are one or two lines saying why.
