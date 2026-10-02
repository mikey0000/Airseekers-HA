# Airseekers Tron for Home Assistant

A Home Assistant integration for the Airseekers Tron robotic mower.

- **Reads** come from the mower's local Foxglove bridge (`ws://<mower-ip>:8765`): pushed in real time, no polling, works without the internet.
- **Writes** go through your Airseekers cloud account, the same path the official app uses.
- **Live video** from the front, left and right cameras plays through Home Assistant's native WebRTC.

Built on [pyairseekers](https://github.com/mikey0000/PyAirseekers), where the protocol details and their evidence levels are documented.

## Entities

| Platform | Source | Entities |
|---|---|---|
| Lawn mower | local state, cloud commands | start, pause, dock |
| Sensor | local | battery, voltage, current, temperature, satellites, GPS quality and SNR, RTK fix, LoRa / Wi-Fi RSSI, mower state, task state / type / runtime, area mowed / remaining, progress |
| Binary sensor | local | charging, cutting, moving, rain, lifted, bumper, emergency stop, alarm, NRTK, routing, battery gate |
| Device tracker | local | GPS position |
| Button | cloud | stop, resume, reboot RTK, clear warnings |
| Number | cloud | volume, light brightness, cut height |
| Switch | cloud | night mode |
| Camera | cloud (WebRTC) | front, left, right |

Service `airseekers_tron.start_mowing_advanced` starts a task with chosen zones and cut settings (height, direction, speed, efficiency, turning).

## Install

1. Add this repository to HACS as a custom integration repository, install **Airseekers Tron**, and restart Home Assistant.
2. Settings → Devices & services → Add integration → **Airseekers Tron**.
3. Sign in with your Airseekers app account, pick your mower, and confirm its local IP address (prefilled from the cloud when it reports one).

The mower and Home Assistant must be on the same network for local reads.

## Development

```bash
uv sync
scripts/develop            # Home Assistant at http://localhost:8123 with this checkout linked in
LOCAL_LIBS=0 scripts/develop   # use the pinned pyairseekers instead of ../PyAirseekers
uv run pytest -p no:homeassistant tests
```

`scripts/develop` links `custom_components/airseekers_tron` into `config/` and, when `../PyAirseekers` exists, links that checkout over the installed `pyairseekers`, so edits to either only need a restart.

Read `CONSTITUTION.md` and `CONTRIBUTING.md` before changing behaviour; decisions are in `docs/decisions.md`.

## Credits

Combines and builds on [Shimmi/airseekers-tron-ha](https://github.com/Shimmi/airseekers-tron-ha) (local Foxglove integration) and [AdrianTIonut/airseekers-tron-ha](https://github.com/AdrianTIonut/airseekers-tron-ha) (cloud integration). MIT licensed; see `LICENSE`.
