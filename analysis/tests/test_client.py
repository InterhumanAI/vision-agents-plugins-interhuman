"""Tests for AnalysisClient using a local HTTP server."""

import json
import socket
from contextlib import closing
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Optional

import pytest

from vision_agents.plugins.interhuman_analysis import (
    AnalysisClient,
    AnalysisResult,
    ConversationQuality,
    ConversationQualityScores,
    InterhumanError,
)


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class _Capture:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    path: str = ""


def _start_server(
    status: int,
    response_body: object,
    response_headers: Optional[dict[str, str]] = None,
    *,
    content_type: str = "application/json",
    raw_response: Optional[bytes] = None,
) -> tuple[ThreadingHTTPServer, _Capture]:
    capture = _Capture(url="")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            capture.headers = {k: v for k, v in self.headers.items()}
            capture.body = self.rfile.read(length)
            capture.path = self.path
            payload = (
                raw_response
                if raw_response is not None
                else json.dumps(response_body).encode("utf-8")
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            for name, value in (response_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    capture.url = f"http://127.0.0.1:{port}"
    Thread(target=server.serve_forever, daemon=True).start()
    return server, capture


@pytest.fixture
def fake_server():
    started: list[ThreadingHTTPServer] = []

    def start(
        status: int = 200,
        body: object = None,
        headers: Optional[dict[str, str]] = None,
        *,
        content_type: str = "application/json",
        raw_response: Optional[bytes] = None,
    ) -> _Capture:
        if body is None and raw_response is None:
            body = {"signals": [], "engagement_state": []}
        server, capture = _start_server(
            status,
            body,
            headers,
            content_type=content_type,
            raw_response=raw_response,
        )
        started.append(server)
        return capture

    yield start

    for s in started:
        s.shutdown()
        s.server_close()


class TestAnalysisClient:
    def test_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("INTERHUMAN_API_KEY", raising=False)
        with pytest.raises(ValueError, match="api_key"):
            AnalysisClient()

    def test_reads_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("INTERHUMAN_API_KEY", "from-env")
        client = AnalysisClient()
        assert client._api_key == "from-env"

    async def test_success_full_payload(self, fake_server):
        body = {
            "engagement_state": [{"start": 0, "end": 10, "state": "engaged"}],
            "signals": [
                {
                    "type": "agreement",
                    "start": 0,
                    "end": 10,
                    "probability": "high",
                    "rationale": "Subject nodded.",
                }
            ],
            "conversation_quality": {
                "overall": {
                    "quality_index": 72,
                    "clarity": 67,
                    "authority": 68,
                    "energy": 80,
                    "rapport": 75,
                    "learning": 70,
                },
                "timeline": [
                    {
                        "start": 0,
                        "end": 10,
                        "values": {
                            "quality_index": 70,
                            "clarity": 69,
                            "authority": 70,
                            "energy": 78,
                            "rapport": 77,
                            "learning": 68,
                        },
                    }
                ],
            },
        }
        capture = fake_server(200, body, {"X-Correlation-ID": "abc"})
        client = AnalysisClient(api_key="key", base_url=capture.url, timeout=5.0)

        result = await client.analyze(
            b"fake-video-bytes",
            include=["conversation_quality_overall", "conversation_quality_timeline"],
        )

        assert isinstance(result, AnalysisResult)
        assert result.correlation_id == "abc"
        assert len(result.signals) == 1
        assert result.signals[0].signal_type == "agreement"
        assert result.signals[0].probability == "high"
        assert result.engagement_state[0].state == "engaged"
        assert isinstance(result.conversation_quality, ConversationQuality)
        assert result.conversation_quality.overall == ConversationQualityScores(
            quality_index=72,
            clarity=67,
            authority=68,
            energy=80,
            rapport=75,
            learning=70,
        )
        assert len(result.conversation_quality.timeline) == 1

    async def test_success_minimal_payload_omits_conversation_quality(self, fake_server):
        body = {
            "engagement_state": [{"start": 0, "end": 5, "state": "neutral"}],
            "signals": [],
        }
        capture = fake_server(200, body)
        client = AnalysisClient(api_key="key", base_url=capture.url, timeout=5.0)

        result = await client.analyze(b"x")

        assert result.signals == []
        assert result.conversation_quality is None
        assert len(result.engagement_state) == 1

    async def test_sends_bearer_and_optional_request_id(self, fake_server):
        capture = fake_server()
        client = AnalysisClient(
            api_key="my-secret", base_url=capture.url, timeout=5.0
        )

        await client.analyze(
            b"video-bytes",
            include=["conversation_quality_overall"],
            client_request_id="req-42",
        )

        assert capture.headers.get("Authorization") == "Bearer my-secret"
        assert capture.headers.get("X-Client-Request-Id") == "req-42"
        assert capture.path == "/v1/upload/analyze"
        # Multipart body should mention the include flag and the file content.
        assert b"conversation_quality_overall" in capture.body
        assert b"video-bytes" in capture.body

    async def test_uploads_from_path(self, fake_server, tmp_path):
        sample = tmp_path / "clip.mp4"
        sample.write_bytes(b"\x00\x00\x00\x18ftypmp42file-content")
        capture = fake_server()
        client = AnalysisClient(api_key="key", base_url=capture.url, timeout=5.0)

        await client.analyze(sample)

        assert b"file-content" in capture.body
        assert b'filename="clip.mp4"' in capture.body
        assert b"video/mp4" in capture.body

    async def test_error_response_raises_interhuman_error(self, fake_server):
        body = {
            "error_id": "ih4007",
            "correlation_id": "f47ac",
            "link": "https://docs.interhuman.ai/api-reference/error-handling#ih4007",
            "message": "Video must be at least 3 seconds.",
        }
        capture = fake_server(400, body)
        client = AnalysisClient(api_key="key", base_url=capture.url, timeout=5.0)

        with pytest.raises(InterhumanError) as excinfo:
            await client.analyze(b"x")

        err = excinfo.value
        assert err.status_code == 400
        assert err.error_id == "ih4007"
        assert err.correlation_id == "f47ac"
        assert "3 seconds" in str(err)

    async def test_error_response_with_non_json_body(self, fake_server):
        capture = fake_server(
            500,
            None,
            content_type="text/html",
            raw_response=b"<html>oops</html>",
        )
        client = AnalysisClient(api_key="key", base_url=capture.url, timeout=5.0)

        with pytest.raises(InterhumanError) as excinfo:
            await client.analyze(b"x")

        assert excinfo.value.status_code == 500
        assert excinfo.value.error_id == ""
