# Constitution

The rules that do not bend for the Airseekers Tron Home Assistant integration.
A change that breaks one needs a new numbered entry in `docs/decisions.md`
that supersedes it. Transport-level rules live in pyairseekers'
`CONSTITUTION.md` and apply here too.

## 1. Local reads, cloud writes

Every read entity is backed by the local push coordinator (`coordinator.py`);
every write entity and the cameras by the cloud coordinator
(`cloud_coordinator.py`). Telemetry is never polled from the cloud. The cloud
is polled only for what commands need, at a slow interval (D3).

## 2. The local bridge is read-only

Nothing in this integration publishes to the Foxglove bridge or calls a ROS
service. Local commands wait on the verification in pyairseekers D3.

## 3. No transport code here

HTTP, WebSocket, ROS decoding and WHEP live in `pyairseekers`. This package
maps library calls to Home Assistant concepts and nothing else. A missing
endpoint is added to the library first.

## 4. Commands never fail silently

Every cloud command goes through `AirseekersCloudCoordinator.async_command`,
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
