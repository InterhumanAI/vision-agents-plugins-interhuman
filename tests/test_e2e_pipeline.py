"""End-to-end pipeline integration test against the live Interhuman API."""

import asyncio
import os
import time
import types

import av
import numpy as np
import pytest
from aiortc import VideoStreamTrack
from getstream.video.rtc import PcmData
from vision_agents.core.events import EventManager

from vision_agents.plugins.interhuman import (
    InterhumanConversationQualityEvent,
    InterhumanEngagementEvent,
    InterhumanProcessor,
    InterhumanRawEvent,
    InterhumanSignalEvent,
)


class _SyntheticVideoTrack(VideoStreamTrack):
    """Synthetic 320x240 yuv420p track that emits a moving gradient."""

    def __init__(self, width: int = 320, height: int = 240) -> None:
        super().__init__()
        self._width = width
        self._height = height
        self._frame_index = 0

    async def recv(self) -> av.VideoFrame:
        pts, time_base = await self.next_timestamp()
        i = self._frame_index
        self._frame_index += 1
        arr = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        arr[:, :, 0] = (i * 7) % 255
        arr[:, :, 1] = (i * 11) % 255
        arr[:, :, 2] = (i * 13) % 255
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        frame = frame.reformat(format="yuv420p")
        frame.pts = pts
        frame.time_base = time_base
        return frame


class _Participant:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


async def _push_audio(processor: InterhumanProcessor, stop: asyncio.Event) -> None:
    samples_per_chunk = 4800
    participant = _Participant(user_id="alice")
    rng = np.random.default_rng(seed=0)
    while not stop.is_set():
        samples = (rng.normal(scale=2000, size=samples_per_chunk)).astype(np.int16)
        pcm = PcmData(
            sample_rate=48000,
            format="s16",
            samples=samples,
            channels=1,
            participant=participant,
        )
        await processor.process_audio(pcm)
        await asyncio.sleep(0.1)


@pytest.mark.integration
async def test_processor_pipeline_emits_typed_events():
    """Drive the processor with a real video track + PCM audio for ~35s.

    Validates that segments are produced, sent, and the API responds with
    typed events that bubble through agent.events without parsing crashes.
    """
    api_key = os.getenv("INTERHUMAN_API_KEY")
    if not api_key:
        pytest.skip("INTERHUMAN_API_KEY not set")

    events = EventManager()
    processor = InterhumanProcessor(
        api_key=api_key,
        include=[
            "conversation_quality_overall",
            "conversation_quality_timeline",
        ],
        window_seconds=5.0,
        video_fps=15,
        video_width=320,
        video_height=240,
    )
    processor.attach_agent(types.SimpleNamespace(events=events))

    received: list = []

    @events.subscribe
    async def on_signal(event: InterhumanSignalEvent) -> None:
        received.append(event)

    @events.subscribe
    async def on_engagement(event: InterhumanEngagementEvent) -> None:
        received.append(event)

    @events.subscribe
    async def on_quality(event: InterhumanConversationQualityEvent) -> None:
        received.append(event)

    @events.subscribe
    async def on_raw(event: InterhumanRawEvent) -> None:
        received.append(event)

    track = _SyntheticVideoTrack()
    stop = asyncio.Event()
    audio_task = asyncio.create_task(_push_audio(processor, stop))
    started = time.monotonic()
    try:
        await processor.process_video(track, participant_id="alice")
        await asyncio.sleep(35.0)
    finally:
        stop.set()
        await audio_task
        await processor.close()
        track.stop()

    typed = [
        e
        for e in received
        if isinstance(
            e,
            (
                InterhumanSignalEvent,
                InterhumanEngagementEvent,
                InterhumanConversationQualityEvent,
            ),
        )
    ]
    raw_errors = [
        e
        for e in received
        if isinstance(e, InterhumanRawEvent)
        and isinstance(e.payload, dict)
        and e.payload.get("type") == "error"
    ]

    elapsed = time.monotonic() - started
    assert typed, f"Expected typed events from Interhuman in {elapsed:.1f}s; got none"
    assert not raw_errors, f"Server returned errors: {[e.payload for e in raw_errors]}"
