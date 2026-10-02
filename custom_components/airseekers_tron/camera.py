"""Camera platform: live video via the vendor's WHEP (SRS) server.

Each WebRTC offer from the frontend gets a freshly minted WHEP URL from
``/api/web/live/open`` (its JWT only lives a few minutes) and is posted to
SRS as-is; the browser then streams directly from SRS. SRS is ICE-lite with
its candidates in the answer, so client candidates are ignored. While a
session is open, ``/api/web/live/heartbeat`` keeps the stream alive.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.camera import (
    Camera,
    CameraEntityFeature,
    WebRTCAnswer,
    WebRTCError,
    WebRTCSendMessage,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyairseekers import AirseekersError, LiveStream, whep_play, whep_stop
from pyairseekers.const import (
    CAMERA_FRONT,
    CAMERA_LEFT,
    CAMERA_RIGHT,
    LIVE_HEARTBEAT_INTERVAL_S,
)
from webrtc_models import RTCIceCandidateInit

from .coordinator import AirseekersTronConfigEntry, AirseekersTronData
from .entity import AirseekersCloudEntity

_LOGGER = logging.getLogger(__name__)

# Translation key per live/open camera index
CAMERAS = {
    CAMERA_FRONT: "front_camera",
    CAMERA_LEFT: "left_camera",
    CAMERA_RIGHT: "right_camera",
}


@dataclass
class _Session:
    stream: LiveStream
    heartbeat: asyncio.Task[None]


async def keep_alive(
    beat: Callable[[], Awaitable[None]],
    interval: float = LIVE_HEARTBEAT_INTERVAL_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Call ``beat`` every ``interval`` seconds until cancelled.

    A failed beat is logged and the loop carries on: one dropped heartbeat
    should not end a session the browser is still showing.
    """
    while True:
        await sleep(interval)
        try:
            await beat()
        except AirseekersError as err:
            _LOGGER.debug("Live heartbeat failed: %s", err)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirseekersTronConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        AirseekersCamera(entry.runtime_data, camera_id) for camera_id in CAMERAS
    )


class AirseekersCamera(AirseekersCloudEntity, Camera):
    """One of the mower's cameras, streamed through the cloud."""

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, data: AirseekersTronData, camera_id: int) -> None:
        AirseekersCloudEntity.__init__(self, data, f"camera_{camera_id}")
        Camera.__init__(self)
        self._camera_id = camera_id
        self._attr_translation_key = CAMERAS[camera_id]
        self._sessions: dict[str, _Session] = {}

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        cloud = self.coordinator
        try:
            url = await cloud.api.open_live_stream(cloud.sn, self._camera_id)
            stream = await whep_play(async_get_clientsession(self.hass), url, offer_sdp)
        except AirseekersError as err:
            _LOGGER.warning("Camera %s: %s", self._camera_id, err)
            send_message(WebRTCError("webrtc_offer_failed", str(err)))
            return
        heartbeat = self.hass.async_create_background_task(
            keep_alive(lambda: cloud.api.live_heartbeat(cloud.sn, self._camera_id)),
            f"{self.entity_id} live heartbeat",
        )
        self._sessions[session_id] = _Session(stream, heartbeat)
        send_message(WebRTCAnswer(stream.answer_sdp))

    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        """SRS is ICE-lite; its candidates are already in the answer."""

    @callback
    def close_webrtc_session(self, session_id: str) -> None:
        if (session := self._sessions.pop(session_id, None)) is not None:
            session.heartbeat.cancel()
            self.hass.async_create_task(
                whep_stop(async_get_clientsession(self.hass), session.stream, _LOGGER)
            )
        super().close_webrtc_session(session_id)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        # Live-only; no snapshot endpoint known yet
        return None

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        for session_id in list(self._sessions):
            self.close_webrtc_session(session_id)
