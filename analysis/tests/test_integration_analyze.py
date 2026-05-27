"""Live integration test for the Interhuman upload-analyze endpoint."""

import io
import os

import pytest

from vision_agents.plugins.interhuman_analysis import AnalysisClient, AnalysisResult


def _build_sample_mp4(seconds: int = 5, fps: int = 15) -> bytes:
    """Build a synthetic MP4 with a moving subject and silence."""
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")

    buf = io.BytesIO()
    container = av.open(buf, mode="w", format="mp4")
    video = container.add_stream("h264", rate=fps)
    video.width = 320
    video.height = 240
    video.pix_fmt = "yuv420p"
    audio = container.add_stream("aac", rate=48000)
    audio.layout = "mono"

    total_frames = seconds * fps
    for i in range(total_frames):
        x = (i * 4) % 240
        arr = np.full((240, 320, 3), 30, dtype=np.uint8)
        arr[x : x + 20, x : x + 20, :] = 220
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        frame.pts = i
        frame = frame.reformat(format="yuv420p")
        for packet in video.encode(frame):
            container.mux(packet)

    samples_per_chunk = 1024
    total_audio_chunks = (seconds * 48000) // samples_per_chunk
    for j in range(total_audio_chunks):
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
def interhuman_sample_mp4() -> bytes:
    return _build_sample_mp4()


@pytest.mark.integration
async def test_live_upload_returns_analysis(interhuman_sample_mp4):
    api_key = os.getenv("INTERHUMAN_API_KEY")
    if not api_key:
        pytest.skip("INTERHUMAN_API_KEY not set")

    client = AnalysisClient(api_key=api_key, timeout=180.0)
    result = await client.analyze(
        interhuman_sample_mp4,
        include=["conversation_quality_overall", "conversation_quality_timeline"],
    )

    assert isinstance(result, AnalysisResult)
    assert result.correlation_id, "expected X-Correlation-ID header"
    assert result.engagement_state, "expected at least one engagement window"
    for window in result.engagement_state:
        assert window.state in {"engaged", "neutral", "disengaged"}
