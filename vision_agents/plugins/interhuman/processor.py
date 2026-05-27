"""Interhuman streaming processor for Vision Agents."""

import asyncio
import logging
import os
from typing import Optional

import aiortc
import av
from getstream.video.rtc import PcmData
from vision_agents.core import Agent
from vision_agents.core.events import EventManager, PluginBaseEvent
from vision_agents.core.processors.base_processor import (
    AudioProcessor,
    VideoProcessor,
)
from vision_agents.core.utils.video_forwarder import VideoForwarder

from vision_agents.plugins.interhuman.events import (
    InterhumanConversationQualityEvent,
    InterhumanEngagementEvent,
    InterhumanRawEvent,
    InterhumanSignalEvent,
)
from vision_agents.plugins.interhuman.segment_builder import SegmentBuilder
from vision_agents.plugins.interhuman.ws_client import WSClient

logger = logging.getLogger(__name__)


class InterhumanProcessor(VideoProcessor, AudioProcessor):
    """Stream call audio+video to Interhuman and emit typed events.

    The processor subscribes to one participant's audio and video, fuses each
    fixed-length window into a WebM segment (VP8 + Opus), and pushes the
    segment to ``wss://api.interhuman.ai/v1/stream/analyze``. Server events
    are re-emitted on the agent's event bus as :class:`InterhumanSignalEvent`,
    :class:`InterhumanEngagementEvent`, :class:`InterhumanConversationQualityEvent`,
    or :class:`InterhumanRawEvent`.

    Args:
        api_key: Interhuman API key. Falls back to ``INTERHUMAN_API_KEY`` env var.
        base_url: Override the API base. Default: ``wss://api.interhuman.ai``.
        include: ``include`` flags sent on connect, e.g.
            ``["conversation_quality_overall", "conversation_quality_timeline"]``.
        window_seconds: Segment length in seconds. Range 3.0–30.0. Default 5.0.
        video_fps: Encoder fps; also drives the VideoForwarder handler rate.
        video_width: Output video width fed to VP8.
        video_height: Output video height fed to VP8.
        video_bitrate: VP8 target bitrate in bits per second.
        audio_bitrate: Opus target bitrate in bits per second.
        target_participant_id: If set, only analyze this participant. Otherwise
            the processor locks onto the first non-agent participant it sees.
        max_outbox_age_seconds: Drop queued segments older than this when
            disconnected.
    """

    name = "interhuman"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "wss://api.interhuman.ai",
        include: Optional[list[str]] = None,
        window_seconds: float = 5.0,
        video_fps: int = 15,
        video_width: int = 640,
        video_height: int = 360,
        video_bitrate: int = 1_000_000,
        audio_bitrate: int = 64_000,
        target_participant_id: Optional[str] = None,
        max_outbox_age_seconds: float = 30.0,
    ) -> None:
        super().__init__()

        resolved_key = api_key or os.getenv("INTERHUMAN_API_KEY")
        if not resolved_key:
            raise ValueError(
                "api_key required (pass api_key= or set INTERHUMAN_API_KEY)"
            )
        if not 3.0 <= window_seconds <= 30.0:
            raise ValueError(
                f"window_seconds must be between 3.0 and 30.0, got {window_seconds}"
            )
        if not 1 <= video_fps <= 30:
            raise ValueError(f"video_fps must be between 1 and 30, got {video_fps}")

        self._api_key = resolved_key
        self._url = f"{base_url.rstrip('/')}/v1/stream/analyze"
        self._include = list(include or [])
        self._window_seconds = window_seconds
        self._video_fps = video_fps
        self._video_width = video_width
        self._video_height = video_height
        self._target_participant_id = target_participant_id
        self._locked_participant_id: Optional[str] = target_participant_id

        self._segment_builder = SegmentBuilder(
            width=video_width,
            height=video_height,
            fps=video_fps,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
            min_segment_seconds=max(3.0, window_seconds * 0.95),
        )
        self._builder_lock = asyncio.Lock()

        self._ws_client = WSClient(
            url=self._url,
            api_key=self._api_key,
            include=self._include,
            on_event=self._dispatch_event,
            plugin_name=self.name,
            max_outbox_age_seconds=max_outbox_age_seconds,
        )

        self._events: Optional[EventManager] = None
        self._video_forwarder: Optional[VideoForwarder] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._closed = False

        logger.info(
            "🧠 Interhuman processor initialized (window=%.1fs)", window_seconds
        )

    @property
    def events(self) -> EventManager:
        if self._events is None:
            raise ValueError("Agent is not attached to the processor yet")
        return self._events

    def attach_agent(self, agent: Agent) -> None:
        self._events = agent.events
        self._events.register(InterhumanSignalEvent)
        self._events.register(InterhumanEngagementEvent)
        self._events.register(InterhumanConversationQualityEvent)
        self._events.register(InterhumanRawEvent)

    async def process_video(
        self,
        track: aiortc.VideoStreamTrack,
        participant_id: Optional[str],
        shared_forwarder: Optional[VideoForwarder] = None,
    ) -> None:
        if self._closed:
            return
        if (
            self._target_participant_id is not None
            and participant_id != self._target_participant_id
        ):
            logger.debug("Ignoring video from participant %s", participant_id)
            return
        if self._locked_participant_id is None and participant_id is not None:
            self._locked_participant_id = participant_id
            logger.info("Interhuman locked onto participant %s", participant_id)
        elif (
            self._locked_participant_id is not None
            and participant_id != self._locked_participant_id
        ):
            logger.debug(
                "Ignoring video from non-locked participant %s", participant_id
            )
            return

        if self._video_forwarder is not None:
            await self._video_forwarder.remove_frame_handler(self._on_frame)

        self._video_forwarder = (
            shared_forwarder
            if shared_forwarder is not None
            else VideoForwarder(track, fps=self._video_fps, name="interhuman_forwarder")
        )
        self._video_forwarder.add_frame_handler(
            self._on_frame, fps=float(self._video_fps), name="interhuman"
        )

        await self._ws_client.start()
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(
                self._flush_loop(), name="interhuman-flush"
            )

    async def stop_processing(self) -> None:
        if self._video_forwarder is not None:
            await self._video_forwarder.remove_frame_handler(self._on_frame)
            self._video_forwarder = None

    async def process_audio(self, audio_data: PcmData) -> None:
        if self._closed:
            return
        participant = audio_data.participant
        participant_id = participant.user_id if participant is not None else None
        if (
            self._target_participant_id is not None
            and participant_id != self._target_participant_id
        ):
            return
        if self._locked_participant_id is None and participant_id is not None:
            self._locked_participant_id = participant_id
            logger.info(
                "Interhuman locked onto participant %s (via audio)", participant_id
            )
        elif (
            self._locked_participant_id is not None
            and participant_id != self._locked_participant_id
        ):
            return

        async with self._builder_lock:
            try:
                self._segment_builder.add_audio(audio_data)
            except Exception:
                logger.exception("Failed to add audio chunk to segment")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self.stop_processing()
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Interhuman flush task raised on close")
            self._flush_task = None
        await self._ws_client.close()
        async with self._builder_lock:
            self._segment_builder.close()
        logger.info("🧠 Interhuman processor closed")

    async def _on_frame(self, frame: av.VideoFrame) -> None:
        if self._closed:
            return
        async with self._builder_lock:
            try:
                self._segment_builder.add_video(frame)
            except Exception:
                logger.exception("Failed to add video frame to segment")

    async def _flush_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self._window_seconds)
                async with self._builder_lock:
                    data = self._segment_builder.flush()
                if data is None:
                    continue
                await self._ws_client.send_segment(data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Interhuman flush loop crashed")

    async def _dispatch_event(self, event: PluginBaseEvent) -> None:
        if self._events is None:
            logger.debug("Dropping event %s before agent is attached", event.type)
            return
        self._events.send(event)
