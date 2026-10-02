# Decisions

Numbered, append-only; supersede, never edit away.

## D1. Hybrid: local reads, cloud writes

Combines Shimmi/airseekers-tron-ha (local Foxglove, read-only) and
AdrianTIonut/airseekers-tron-ha (cloud, read + write). Reads come from the
local bridge because it pushes in real time and works without the internet;
writes go through the cloud because local command schemas and safe-stop are
unverified (pyairseekers D3). Revisit when local commands are verified.

## D2. Transport code moved to pyairseekers

The Foxglove client, ROS1 decoder, cloud client and WHEP helper live in the
`pyairseekers` package; the integration requires it. Reason: the local repo
already planned the extraction, the cloud client was duplicated per platform,
and a library can be tested without Home Assistant.

## D3. The cloud coordinator polls slowly, and refreshes before deciding

Default 300 s (option 30-3600). It holds the device online flag, scheduled
tasks, maps, legacy-task state and config values. Start, resume and
`start_mowing_advanced` call `async_refresh()` first, because legacy-task
state changes when the mower docks and a five-minute-old snapshot would pick
the wrong path.

## D4. Start resolution order

Pending legacy task (continue it via `task/start` with `legacy_task_id`) →
first scheduled task → most recent executed task. Resume uses `task/resume`
only when the cloud says paused (`state == 2`); otherwise a legacy task is
restarted. Inherited from the cloud integration, where `task/resume` was found
to no-op for legacy tasks.

## D5. Config flow order: cloud, device, local

The cloud login comes first because it yields the serial number (the unique
id and device identifier) and the mower's Wi-Fi IP, which prefills the local
step. Entries are `VERSION = 2`; local-only v1 entries have no credentials and
are not migrated: remove and re-add.

## D6. Cameras are native WebRTC, one entity per index

One camera entity per index implements
`async_handle_async_webrtc_offer`: mint a WHEP URL, post the browser's offer,
return the answer, DELETE the session on close. No snapshot (no endpoint
known). Names are numbers until pyairseekers Q1 is answered.

## D7. Dropped stub entities

The cloud integration's "Mowing mode" select and "Lock mode" switch sent
nothing (endpoint unknown, password unknown). Start, pause and dock buttons
duplicated the lawn_mower entity. None were carried over; `stop`, `resume`,
`rtk_reboot` and `clean_warn` remain as buttons.

## D8. Night mode remembers its schedule

Turning night mode off writes `SetDarkMode = ""`, which loses the hours. The
switch keeps the last non-empty schedule (cloud value, else restored state
attribute `schedule`, else 22:00-06:00) and writes it back on turn-on.

## D9. Cut height follows the app

30-90 mm in steps of 10, stored on the first scheduled task (`PUT task`).
Without a scheduled task the write fails loudly rather than guessing.

## D10. Cameras are named front, left, right

Supersedes the naming in D6. The owner of a Tron confirmed `live/open` camera
1 is the front camera, 2 the left and 3 the right
(`pyairseekers.const.CAMERA_*`). Entities are `Front camera`, `Left camera`
and `Right camera`; unique ids stay `<sn>_camera_<index>` so a rename never
orphans an entity.

## D11. A heartbeat per viewing session

The cloud only keeps a stream alive while the viewer calls
`POST /api/web/live/heartbeat {sn, camera}`. Each WebRTC session starts a
background task (`camera.py::keep_alive`) that beats every
`pyairseekers.const.LIVE_HEARTBEAT_INTERVAL_S` (10 s until the app's interval
is captured, pyairseekers Q12) and is cancelled in `close_webrtc_session`.
Stopping the heartbeat is how the robot side ends; there is no known close
call. A failed beat is logged at debug and the loop continues, so a single
dropped request does not cut a stream the user is watching.

## D12. Heartbeat every 20 seconds

Refines D11. The app was captured sending heartbeats 38 s apart; the
integration uses pyairseekers' `LIVE_HEARTBEAT_INTERVAL_S` (20 s), which
stays inside that gap even if the capture missed a beat in between.
