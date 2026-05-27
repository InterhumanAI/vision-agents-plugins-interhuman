"""Tests for InterhumanProcessor input validation and lifecycle behavior."""

import numpy as np
import pytest
from getstream.video.rtc import PcmData

from vision_agents.plugins.interhuman_streaming import InterhumanProcessor


def _pcm(duration_ms: float, participant_id: str) -> PcmData:
    n = int(48000 * duration_ms / 1000.0)
    samples = np.zeros(n, dtype=np.int16)
    pcm = PcmData(samples=samples, sample_rate=48000, format="s16", channels=1)
    pcm.participant = type("P", (), {"user_id": participant_id})()
    return pcm


class TestInterhumanProcessor:
    def test_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("INTERHUMAN_API_KEY", raising=False)
        with pytest.raises(ValueError, match="api_key"):
            InterhumanProcessor()

    def test_validates_window_seconds_low(self):
        with pytest.raises(ValueError, match="window_seconds"):
            InterhumanProcessor(api_key="x", window_seconds=2.5)

    def test_validates_window_seconds_high(self):
        with pytest.raises(ValueError, match="window_seconds"):
            InterhumanProcessor(api_key="x", window_seconds=30.5)

    def test_validates_video_fps(self):
        with pytest.raises(ValueError, match="video_fps"):
            InterhumanProcessor(api_key="x", video_fps=0)

    def test_reads_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("INTERHUMAN_API_KEY", "from-env")
        proc = InterhumanProcessor()
        assert proc._api_key == "from-env"

    def test_name(self):
        proc = InterhumanProcessor(api_key="x")
        assert proc.name == "interhuman"

    async def test_process_audio_locks_onto_first_participant(self):
        proc = InterhumanProcessor(api_key="x", window_seconds=5.0)
        # Stub the segment builder so we can observe what got fed in.
        observed: list[str] = []

        def fake_add_audio(pcm):
            observed.append(pcm.participant.user_id)

        proc._segment_builder.add_audio = fake_add_audio  # type: ignore[assignment]

        await proc.process_audio(_pcm(20, "alice"))
        await proc.process_audio(_pcm(20, "bob"))
        await proc.process_audio(_pcm(20, "alice"))

        assert observed == ["alice", "alice"]

    async def test_close_is_idempotent(self):
        proc = InterhumanProcessor(api_key="x")
        await proc.close()
        await proc.close()
