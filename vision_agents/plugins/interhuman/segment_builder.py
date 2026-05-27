"""Mux video frames and PCM audio into a self-contained WebM segment."""

import fractions
import io
import logging
from typing import Optional

import av
import numpy as np
from getstream.video.rtc import PcmData

logger = logging.getLogger(__name__)


class SegmentBuilder:
    """Build one WebM segment per call to :meth:`flush`.

    The builder owns a ``BytesIO`` and a PyAV output container with a VP8
    video stream and (lazily) an Opus audio stream. Frames and audio chunks
    are encoded immediately so :meth:`flush` only needs to write the trailer.

    Both video and audio streams are added up front because PyAV cannot add
    streams to a WebM container after packets have been muxed. If no audio is
    fed before :meth:`flush`, the segment is re-muxed video-only.

    Args:
        width: Output video width.
        height: Output video height.
        fps: Video frame rate written to the container.
        video_bitrate: VP8 target bitrate, bits per second.
        audio_sample_rate: Sample rate fed to libopus. Input PCM is resampled
            to this rate as needed.
        audio_bitrate: Opus target bitrate, bits per second.
        min_segment_seconds: On flush, pad video by repeating the last frame
            until the declared video duration reaches this minimum. Avoids
            short-segment rejections from the upstream service when input
            frame rate dips. ``0.0`` disables padding.
    """

    def __init__(
        self,
        *,
        width: int,
        height: int,
        fps: int,
        video_bitrate: int = 1_000_000,
        audio_sample_rate: int = 48000,
        audio_bitrate: int = 64_000,
        min_segment_seconds: float = 3.0,
    ) -> None:
        self._width = width
        self._height = height
        self._fps = fps
        self._video_bitrate = video_bitrate
        self._audio_sample_rate = audio_sample_rate
        self._audio_bitrate = audio_bitrate
        self._min_segment_seconds = min_segment_seconds

        self._buffer: Optional[io.BytesIO] = None
        self._container: Optional[av.container.OutputContainer] = None
        self._video_stream: Optional[av.video.stream.VideoStream] = None
        self._audio_stream: Optional[av.audio.stream.AudioStream] = None
        self._audio_resampler: Optional[av.AudioResampler] = None

        self._video_frame_index = 0
        self._audio_pts = 0
        self._has_video = False
        self._has_audio = False
        self._last_video_frame: Optional[av.VideoFrame] = None

        self._open_container()

    def _open_container(self) -> None:
        self._buffer = io.BytesIO()
        self._container = av.open(self._buffer, mode="w", format="webm")
        video_stream = self._container.add_stream("vp8", rate=self._fps)
        assert isinstance(video_stream, av.video.stream.VideoStream)
        video_stream.width = self._width
        video_stream.height = self._height
        video_stream.pix_fmt = "yuv420p"
        video_stream.bit_rate = self._video_bitrate
        video_stream.time_base = fractions.Fraction(1, self._fps)
        self._video_stream = video_stream

        audio_stream = self._container.add_stream(
            "libopus", rate=self._audio_sample_rate
        )
        assert isinstance(audio_stream, av.audio.stream.AudioStream)
        audio_stream.bit_rate = self._audio_bitrate
        audio_stream.layout = "mono"
        audio_stream.time_base = fractions.Fraction(1, self._audio_sample_rate)
        self._audio_stream = audio_stream

        self._audio_resampler = None
        self._video_frame_index = 0
        self._audio_pts = 0
        self._has_video = False
        self._has_audio = False
        self._last_video_frame = None

    def _ensure_audio_resampler(self, sample_rate: int, channels: int) -> None:
        if self._audio_resampler is not None or sample_rate == self._audio_sample_rate:
            return
        layout = "mono" if channels == 1 else "stereo"
        self._audio_resampler = av.AudioResampler(
            format="s16",
            layout=layout,
            rate=self._audio_sample_rate,
        )
        logger.debug(
            "SegmentBuilder: created audio resampler %d Hz -> %d Hz",
            sample_rate,
            self._audio_sample_rate,
        )

    def add_video(self, frame: av.VideoFrame) -> None:
        """Append a video frame to the in-progress segment.

        Resizes/converts the frame to the configured output format if needed.
        """
        assert self._container is not None and self._video_stream is not None
        if frame.width != self._width or frame.height != self._height:
            frame = frame.reformat(
                width=self._width, height=self._height, format="yuv420p"
            )
        elif frame.format.name != "yuv420p":
            frame = frame.reformat(format="yuv420p")

        frame.pts = self._video_frame_index
        frame.time_base = fractions.Fraction(1, self._fps)
        self._video_frame_index += 1
        self._has_video = True
        self._last_video_frame = frame

        for packet in self._video_stream.encode(frame):
            self._container.mux(packet)

    def add_audio(self, pcm: PcmData) -> None:
        """Append a chunk of PCM audio. Resamples to the configured rate."""
        assert self._container is not None and self._audio_stream is not None
        self._ensure_audio_resampler(pcm.sample_rate, pcm.channels)

        layout = "mono" if pcm.channels == 1 else "stereo"
        samples = np.ascontiguousarray(pcm.samples, dtype=np.int16)
        if pcm.channels == 1:
            samples = samples.reshape(1, -1)
        else:
            samples = samples.reshape(-1, pcm.channels).T
            samples = np.ascontiguousarray(samples)

        in_frame = av.AudioFrame.from_ndarray(samples, format="s16", layout=layout)
        in_frame.sample_rate = pcm.sample_rate
        in_frame.pts = None

        frames_to_encode = [in_frame]
        if self._audio_resampler is not None:
            frames_to_encode = list(self._audio_resampler.resample(in_frame))

        for audio_frame in frames_to_encode:
            audio_frame.pts = self._audio_pts
            audio_frame.time_base = fractions.Fraction(1, self._audio_sample_rate)
            self._audio_pts += audio_frame.samples
            for packet in self._audio_stream.encode(audio_frame):
                self._container.mux(packet)
        self._has_audio = True

    def flush(self) -> Optional[bytes]:
        """Close the current segment and return its bytes.

        Returns ``None`` if no video frames were written. After flushing, a
        new empty container is opened automatically for the next window.
        """
        assert self._container is not None and self._buffer is not None

        if not self._has_video:
            return None

        try:
            assert self._video_stream is not None
            self._pad_video_to_min_duration()
            for packet in self._video_stream.encode():
                self._container.mux(packet)
            if self._has_audio and self._audio_stream is not None:
                if self._audio_resampler is not None:
                    for resampled in self._audio_resampler.resample(None) or []:
                        resampled.pts = self._audio_pts
                        resampled.time_base = fractions.Fraction(
                            1, self._audio_sample_rate
                        )
                        self._audio_pts += resampled.samples
                        for packet in self._audio_stream.encode(resampled):
                            self._container.mux(packet)
                for packet in self._audio_stream.encode():
                    self._container.mux(packet)
            self._container.close()

            data = self._buffer.getvalue()

            if not self._has_audio:
                buffer_no_audio = io.BytesIO()
                container_out = av.open(buffer_no_audio, mode="w", format="webm")
                video_out = container_out.add_stream("vp8", rate=self._fps)
                assert isinstance(video_out, av.video.stream.VideoStream)
                video_out.width = self._width
                video_out.height = self._height
                video_out.pix_fmt = "yuv420p"
                video_out.bit_rate = self._video_bitrate
                video_out.time_base = fractions.Fraction(1, self._fps)

                container_in = av.open(io.BytesIO(data), mode="r")
                for packet in container_in.demux(video=0):
                    container_out.mux(packet)
                container_in.close()
                container_out.close()
                data = buffer_no_audio.getvalue()
        except Exception:
            logger.exception("SegmentBuilder flush failed")
            self._open_container()
            return None

        self._open_container()
        return data

    def _pad_video_to_min_duration(self) -> None:
        if self._min_segment_seconds <= 0.0 or self._last_video_frame is None:
            return
        assert self._container is not None and self._video_stream is not None
        target_frames = int(self._min_segment_seconds * self._fps)
        while self._video_frame_index < target_frames:
            pad = self._last_video_frame
            pad.pts = self._video_frame_index
            pad.time_base = fractions.Fraction(1, self._fps)
            self._video_frame_index += 1
            for packet in self._video_stream.encode(pad):
                self._container.mux(packet)

    def close(self) -> None:
        """Discard any in-flight container without producing bytes."""
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                logger.exception("SegmentBuilder close failed")
        self._buffer = None
        self._container = None
        self._video_stream = None
        self._audio_stream = None
        self._audio_resampler = None
