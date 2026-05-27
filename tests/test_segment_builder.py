"""Tests for the WebM SegmentBuilder."""

import io

import av
import numpy as np
from getstream.video.rtc import PcmData

from vision_agents.plugins.interhuman.segment_builder import SegmentBuilder


def _make_video_frame(width: int, height: int, color: int) -> av.VideoFrame:
    arr = np.full((height, width, 3), color, dtype=np.uint8)
    frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
    return frame


def _make_pcm(duration_ms: float, sample_rate: int = 48000) -> PcmData:
    n = int(sample_rate * duration_ms / 1000.0)
    samples = np.zeros(n, dtype=np.int16)
    return PcmData(
        samples=samples,
        sample_rate=sample_rate,
        format="s16",
        channels=1,
    )


class TestSegmentBuilder:
    def test_flush_empty_returns_none(self):
        builder = SegmentBuilder(width=320, height=240, fps=15)
        assert builder.flush() is None

    def test_video_only_segment_is_decodable(self):
        builder = SegmentBuilder(width=320, height=240, fps=15)
        # 30 frames at 15 fps = 2 s of video.
        for i in range(30):
            builder.add_video(_make_video_frame(320, 240, color=(i * 7) % 255))
        data = builder.flush()
        assert data is not None
        assert len(data) > 1024  # not pathologically small

        container = av.open(io.BytesIO(data), mode="r")
        assert container.format.name == "matroska,webm"
        video_streams = [s for s in container.streams if s.type == "video"]
        audio_streams = [s for s in container.streams if s.type == "audio"]
        assert len(video_streams) == 1
        assert len(audio_streams) == 0
        container.close()

    def test_video_and_audio_segment_has_both_streams(self):
        builder = SegmentBuilder(width=320, height=240, fps=15)
        for i in range(30):
            builder.add_video(_make_video_frame(320, 240, color=(i * 7) % 255))
        # ~2 s of audio in 100 ms chunks.
        for _ in range(20):
            builder.add_audio(_make_pcm(100))
        data = builder.flush()
        assert data is not None

        container = av.open(io.BytesIO(data), mode="r")
        video_streams = [s for s in container.streams if s.type == "video"]
        audio_streams = [s for s in container.streams if s.type == "audio"]
        assert len(video_streams) == 1
        assert len(audio_streams) == 1
        assert audio_streams[0].codec.name == "opus"
        assert video_streams[0].codec.name == "vp8"
        container.close()

    def test_flush_resets_for_next_window(self):
        builder = SegmentBuilder(width=320, height=240, fps=15)
        for i in range(30):
            builder.add_video(_make_video_frame(320, 240, color=(i * 7) % 255))
        first = builder.flush()
        assert first is not None

        # Second window starts fresh.
        for i in range(30):
            builder.add_video(_make_video_frame(320, 240, color=(i * 11) % 255))
        second = builder.flush()
        assert second is not None
        assert first != second  # different content, not reusing the buffer

    def test_pads_video_to_min_segment_seconds(self):
        # Builder configured for 5 s windows but only 1 s of video supplied.
        builder = SegmentBuilder(
            width=320, height=240, fps=15, min_segment_seconds=5.0
        )
        for i in range(15):  # 1 s of input
            builder.add_video(_make_video_frame(320, 240, color=(i * 7) % 255))
        data = builder.flush()
        assert data is not None

        container = av.open(io.BytesIO(data), mode="r")
        video = next(s for s in container.streams if s.type == "video")
        frame_count = sum(1 for _ in container.decode(video))
        container.close()
        # Expect at least 5 s * 15 fps = 75 frames after padding.
        assert frame_count >= 75, f"got only {frame_count} frames"

    def test_padding_disabled_when_min_zero(self):
        builder = SegmentBuilder(
            width=320, height=240, fps=15, min_segment_seconds=0.0
        )
        for i in range(15):
            builder.add_video(_make_video_frame(320, 240, color=(i * 7) % 255))
        data = builder.flush()
        assert data is not None

        container = av.open(io.BytesIO(data), mode="r")
        video = next(s for s in container.streams if s.type == "video")
        frame_count = sum(1 for _ in container.decode(video))
        container.close()
        assert frame_count == 15

    def test_resamples_audio_when_input_rate_differs(self):
        builder = SegmentBuilder(width=320, height=240, fps=15, audio_sample_rate=48000)
        for i in range(30):
            builder.add_video(_make_video_frame(320, 240, color=(i * 7) % 255))
        # Feed 16 kHz audio; builder must resample to 48 kHz internally.
        for _ in range(20):
            builder.add_audio(_make_pcm(100, sample_rate=16000))
        data = builder.flush()
        assert data is not None

        container = av.open(io.BytesIO(data), mode="r")
        audio = next(s for s in container.streams if s.type == "audio")
        assert audio.codec.name == "opus"
        container.close()
