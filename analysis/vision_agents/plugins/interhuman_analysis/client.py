"""HTTP client for the Interhuman upload-analysis API."""

import logging
import os
from pathlib import Path
from typing import Optional, Union

import httpx

from vision_agents.plugins.interhuman_analysis.types import (
    AnalysisResult,
    ConversationQuality,
    ConversationQualityScores,
    ConversationQualityWindow,
    EngagementWindow,
    Signal,
)

logger = logging.getLogger(__name__)

FileInput = Union[str, Path, bytes]


class InterhumanError(Exception):
    """Raised when the Interhuman API returns a structured error response."""

    def __init__(
        self,
        *,
        status_code: int,
        error_id: str,
        message: str,
        correlation_id: str,
        link: str,
    ) -> None:
        self.status_code = status_code
        self.error_id = error_id
        self.correlation_id = correlation_id
        self.link = link
        super().__init__(f"[{status_code} {error_id}] {message}")


class AnalysisClient:
    """Client for ``POST /v1/upload/analyze``.

    Args:
        api_key: Interhuman API key. Falls back to ``INTERHUMAN_API_KEY`` env var.
        base_url: Override the API base. Default: ``https://api.interhuman.ai``.
        timeout: Per-request timeout in seconds. Server is synchronous; large
            files can take 1–3 minutes.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.interhuman.ai",
        timeout: float = 300.0,
    ) -> None:
        resolved_key = api_key or os.getenv("INTERHUMAN_API_KEY")
        if not resolved_key:
            raise ValueError(
                "api_key required (pass api_key= or set INTERHUMAN_API_KEY)"
            )
        self._api_key = resolved_key
        self._url = f"{base_url.rstrip('/')}/v1/upload/analyze"
        self._timeout = timeout

    async def analyze(
        self,
        file: FileInput,
        *,
        include: Optional[list[str]] = None,
        client_request_id: Optional[str] = None,
    ) -> AnalysisResult:
        """Upload a video file and return the full analysis.

        Args:
            file: Path-like or raw bytes. Supported formats: mp4, avi, mov, mkv,
                mpeg-ts, webm. The file must be 10 KB–32 MB and at least
                ~3 seconds long.
            include: Optional flags. ``conversation_quality_overall`` and/or
                ``conversation_quality_timeline``.
            client_request_id: Sent as ``X-Client-Request-Id`` for log correlation.

        Returns:
            Parsed :class:`AnalysisResult`.

        Raises:
            InterhumanError: When the server returns a structured error response.
            httpx.HTTPError: For network-level failures.
        """
        filename, content = _prepare_file(file)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        if client_request_id is not None:
            headers["X-Client-Request-Id"] = client_request_id

        files: list[tuple[str, tuple[Optional[str], bytes, Optional[str]]]] = [
            ("file", (filename, content, _guess_content_type(filename))),
        ]
        for flag in include or []:
            files.append(("include[]", (None, flag.encode("utf-8"), None)))

        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.post(self._url, headers=headers, files=files)

        correlation_id = response.headers.get("X-Correlation-ID", "")
        if response.status_code >= 400:
            _raise_for_error(response, correlation_id)

        return _parse_result(response.json(), correlation_id)


def _prepare_file(file: FileInput) -> tuple[str, bytes]:
    if isinstance(file, bytes):
        return "upload.bin", file
    path = Path(file)
    return path.name, path.read_bytes()


def _guess_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "webm": "video/webm",
        "mkv": "video/x-matroska",
        "avi": "video/x-msvideo",
        "ts": "video/mp2t",
    }.get(suffix, "application/octet-stream")


def _raise_for_error(response: httpx.Response, correlation_id: str) -> None:
    error_id = ""
    message = response.text
    link = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error_id = body.get("error_id") or ""
        message = body.get("message") or message
        link = body.get("link") or ""
        correlation_id = body.get("correlation_id") or correlation_id
    raise InterhumanError(
        status_code=response.status_code,
        error_id=error_id,
        message=message,
        correlation_id=correlation_id,
        link=link,
    )


def _parse_result(body: dict, correlation_id: str) -> AnalysisResult:
    signals = [
        Signal(
            signal_type=s["type"],
            start=float(s.get("start", 0.0)),
            end=float(s.get("end", 0.0)),
            probability=s.get("probability", "low"),
            rationale=s.get("rationale", ""),
        )
        for s in body.get("signals") or []
    ]
    engagement_state = [
        EngagementWindow(
            start=float(e.get("start", 0.0)),
            end=float(e.get("end", 0.0)),
            state=e.get("state", "neutral"),
        )
        for e in body.get("engagement_state") or []
    ]

    cq_data = body.get("conversation_quality")
    conversation_quality: Optional[ConversationQuality] = None
    if isinstance(cq_data, dict):
        overall = (
            ConversationQualityScores(**cq_data["overall"])
            if cq_data.get("overall")
            else None
        )
        timeline = [
            ConversationQualityWindow(
                start=float(w["start"]),
                end=float(w["end"]),
                values=ConversationQualityScores(**w["values"]),
            )
            for w in (cq_data.get("timeline") or [])
        ]
        conversation_quality = ConversationQuality(overall=overall, timeline=timeline)

    return AnalysisResult(
        signals=signals,
        engagement_state=engagement_state,
        conversation_quality=conversation_quality,
        correlation_id=correlation_id,
    )
