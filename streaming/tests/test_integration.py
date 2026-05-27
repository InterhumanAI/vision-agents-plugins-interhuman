"""Live integration test for the Interhuman streaming endpoint."""

import asyncio
import io
import os

import av
import numpy as np
import pytest

from vision_agents.plugins.interhuman_streaming.events import (
    InterhumanConversationQualityEvent,
    InterhumanEngagementEvent,
    InterhumanRawEvent,
    InterhumanSignalEvent,
)
from vision_agents.plugins.interhuman_streaming.ws_client import WSClient


def _build_sample(seconds: int = 6, fps: int = 15) -> bytes:
    """Build a synthetic WebM segment with video and audio tracks."""
    buf = io.BytesIO()
    container = av.open(buf, mode="w", format="webm")
    video = container.add_stream("vp8", rate=fps)
    video.width = 320
    video.height = 240
    video.pix_fmt = "yuv420p"
    audio = container.add_stream("libopus", rate=48000)
    audio.layout = "mono"

    total_frames = seconds * fps
    for i in range(total_frames):
        arr = np.full((240, 320, 3), (i * 5) % 255, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        frame.pts = i
        frame = frame.reformat(format="yuv420p")
        for packet in video.encode(frame):
            container.mux(packet)

    samples_per_chunk = 48000 // 10  # 100 ms
    for j in range(seconds * 10):
        s = np.zeros((1, samples_per_chunk), dtype=np.int16)
        a = av.AudioFrame.from_ndarray(s, format="s16", layout="mono")
        a.sample_rate = 48000
        a.pts = j * samples_per_chunk
        for packet in audio.encode(a):
            container.mux(packet)

    for packet in video.encode():
        container.mux(packet)
    for packet in audio.encode():
        container.mux(packet)
    container.close()
    return buf.getvalue()


@pytest.fixture(scope="session")
def interhuman_sample_webm() -> bytes:
    """Return the bytes of a small valid WebM segment."""
    return _build_sample()


@pytest.mark.integration
async def test_live_segment_yields_event(interhuman_sample_webm):
    api_key = os.getenv("INTERHUMAN_API_KEY")
    if not api_key:
        pytest.skip("INTERHUMAN_API_KEY not set")

    received: list = []

    async def on_event(event):
        received.append(event)

    client = WSClient(
        url="wss://api.interhuman.ai/v1/stream/analyze",
        api_key=api_key,
        include=["conversation_quality_overall"],
        on_event=on_event,
        plugin_name="interhuman",
    )
    await client.start()
    try:
        await client.send_segment(interhuman_sample_webm)
        await client.send_segment(interhuman_sample_webm)
        for _ in range(60):
            if any(
                isinstance(
                    e,
                    (
                        InterhumanSignalEvent,
                        InterhumanEngagementEvent,
                        InterhumanConversationQualityEvent,
                    ),
                )
                for e in received
            ):
                break
            await asyncio.sleep(1.0)
    finally:
        await client.close()

    raw = [e for e in received if isinstance(e, InterhumanRawEvent)]
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
    assert typed or raw, (
        "Expected at least one event from Interhuman; got nothing in 60s. "
        f"Last raw payloads: {[r.payload for r in raw][-3:]}"
    )
