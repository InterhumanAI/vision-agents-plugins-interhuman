"""WebSocket client for the Interhuman streaming API."""

import asyncio
import collections
import json
import logging
import time
from typing import Awaitable, Callable, Literal, Optional

import websockets
import websockets.exceptions

from vision_agents.core.events import PluginBaseEvent
from vision_agents.plugins.interhuman.events import (
    ConversationQualityScores,
    ConversationQualityWindow,
    InterhumanConversationQualityEvent,
    InterhumanEngagementEvent,
    InterhumanRawEvent,
    InterhumanSignalEvent,
)

logger = logging.getLogger(__name__)


_SIGNAL_PHASES: dict[str, Literal["detected", "updated", "ended"]] = {
    "signal.detected": "detected",
    "signal.updated": "updated",
    "signal.ended": "ended",
}


def parse_server_event(msg: dict, plugin_name: str) -> list[PluginBaseEvent]:
    """Parse one Interhuman server message into a list of typed events.

    Args:
        msg: Raw decoded JSON message from the server.
        plugin_name: Plugin name to attach to emitted events.

    Returns:
        List of typed events. May be empty (e.g. for ``session.ready``).
    """
    msg_type = msg.get("type", "")
    correlation_id = msg.get("correlation_id", "")
    data = msg.get("data", {}) or {}

    if msg_type in _SIGNAL_PHASES:
        return [
            InterhumanSignalEvent(
                plugin_name=plugin_name,
                phase=_SIGNAL_PHASES[msg_type],
                signal_type=data.get("signal_type", ""),
                start=float(data.get("start", 0.0)),
                end=(float(data["end"]) if data.get("end") is not None else None),
                probability=data.get("probability"),
                rationale=data.get("rationale", ""),
                correlation_id=correlation_id,
            )
        ]

    if msg_type == "engagement.updated":
        return [
            InterhumanEngagementEvent(
                plugin_name=plugin_name,
                state=data.get("state", "neutral"),
                start=float(data.get("start", 0.0)),
                correlation_id=correlation_id,
            )
        ]

    if msg_type == "conversation_quality.updated":
        overall: Optional[ConversationQualityScores] = None
        if "overall" in data and data["overall"]:
            overall = ConversationQualityScores(**data["overall"])
        timeline = [
            ConversationQualityWindow(
                start=float(w["start"]),
                end=float(w["end"]),
                values=ConversationQualityScores(**w["values"]),
            )
            for w in (data.get("timeline") or [])
        ]
        return [
            InterhumanConversationQualityEvent(
                plugin_name=plugin_name,
                overall=overall,
                timeline=timeline,
                correlation_id=correlation_id,
            )
        ]

    if msg_type in ("session.ready", "session.updated"):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Interhuman %s: %s", msg_type, data)
        return []

    if msg_type == "error":
        logger.error("Interhuman server error: %s", data)
        return [InterhumanRawEvent(plugin_name=plugin_name, payload=msg)]

    return [InterhumanRawEvent(plugin_name=plugin_name, payload=msg)]


EventCallback = Callable[[PluginBaseEvent], Awaitable[None]]


class WSClient:
    """Long-lived upstream WebSocket client with auto-reconnect.

    The client owns one connection at a time. Outgoing segments are queued so
    the encode path never blocks on the network; queued segments older than
    ``max_outbox_age_seconds`` are dropped to bound memory while disconnected.

    Args:
        url: Full ``wss://`` (or ``ws://`` for tests) URL of the Interhuman
            stream endpoint.
        api_key: Interhuman API key. Sent as ``Authorization: Bearer ...``.
        include: Values for the post-connect ``include`` config message.
        on_event: Async callback invoked for each parsed server event.
        plugin_name: Plugin name attached to emitted events.
        max_outbox_age_seconds: Drop queued segments older than this.
        backoff_initial_seconds: Initial reconnect delay.
        backoff_max_seconds: Cap for the reconnect delay.
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        include: list[str],
        on_event: EventCallback,
        plugin_name: str,
        max_outbox_age_seconds: float = 30.0,
        backoff_initial_seconds: float = 1.0,
        backoff_max_seconds: float = 30.0,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._include = list(include)
        self._on_event = on_event
        self._plugin_name = plugin_name
        self._max_outbox_age = max_outbox_age_seconds
        self._backoff_initial = backoff_initial_seconds
        self._backoff_max = backoff_max_seconds

        self._outbox: collections.deque[tuple[float, bytes]] = collections.deque()
        self._outbox_event = asyncio.Event()
        self._closed = False
        self._auth_failed = False
        self._task: Optional[asyncio.Task] = None
        self._ws: Optional[websockets.ClientConnection] = None
        self._connected_event = asyncio.Event()

    async def start(self) -> None:
        """Spawn the background run loop. Idempotent."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="interhuman-ws")

    async def send_segment(self, data: bytes) -> None:
        """Queue a binary segment for upload. Returns immediately."""
        if self._closed or self._auth_failed:
            return
        self._outbox.append((time.monotonic(), data))
        self._outbox_event.set()

    async def update_include(self, include: list[str]) -> None:
        """Update the config sent on connect; pushes immediately if connected."""
        self._include = list(include)
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"include": self._include}))
            except (websockets.exceptions.WebSocketException, OSError):
                logger.warning(
                    "Failed to push updated include; will retry on reconnect"
                )

    async def close(self) -> None:
        """Stop the run loop and close the connection."""
        self._closed = True
        self._outbox_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("WSClient task ended with an exception")
            self._task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                logger.debug("Ignoring error closing ws", exc_info=True)
            self._ws = None

    async def _run(self) -> None:
        backoff = self._backoff_initial
        while not self._closed and not self._auth_failed:
            try:
                async with websockets.connect(
                    self._url,
                    additional_headers={"Authorization": f"Bearer {self._api_key}"},
                    max_size=64 * 1024 * 1024,
                ) as ws:
                    self._ws = ws
                    self._connected_event.set()
                    backoff = self._backoff_initial
                    await ws.send(json.dumps({"include": self._include}))
                    await asyncio.gather(
                        self._send_loop(ws),
                        self._recv_loop(ws),
                    )
            except websockets.exceptions.InvalidStatus as e:
                if e.response is not None and e.response.status_code in (401, 403):
                    logger.error(
                        "Interhuman auth failed (HTTP %s); not reconnecting",
                        e.response.status_code,
                    )
                    self._auth_failed = True
                    return
                logger.warning(
                    "Interhuman handshake failed: %s; retry in %.1fs", e, backoff
                )
            except (
                websockets.exceptions.WebSocketException,
                OSError,
                ConnectionError,
                TimeoutError,
            ) as e:
                logger.warning(
                    "Interhuman connection error: %s; retry in %.1fs", e, backoff
                )
            except asyncio.CancelledError:
                raise
            finally:
                self._ws = None
                self._connected_event.clear()

            if self._closed:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._backoff_max)

    async def _send_loop(self, ws: websockets.ClientConnection) -> None:
        while not self._closed:
            await self._outbox_event.wait()
            self._outbox_event.clear()
            now = time.monotonic()
            while self._outbox:
                ts, data = self._outbox[0]
                if now - ts > self._max_outbox_age:
                    self._outbox.popleft()
                    logger.warning(
                        "Dropped Interhuman segment older than %.1fs",
                        self._max_outbox_age,
                    )
                    continue
                self._outbox.popleft()
                await ws.send(data)

    async def _recv_loop(self, ws: websockets.ClientConnection) -> None:
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    logger.debug("Ignoring unexpected binary message from server")
                    continue
                try:
                    payload = json.loads(msg)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON text frame from Interhuman: %s", msg[:200])
                    continue
                try:
                    parsed = parse_server_event(payload, self._plugin_name)
                except Exception:
                    logger.exception(
                        "Failed to parse Interhuman server event: %s", payload
                    )
                    continue
                for event in parsed:
                    try:
                        await self._on_event(event)
                    except Exception:
                        logger.exception("on_event callback raised")
        finally:
            # Wake _send_loop so it observes the closed connection and exits via
            # ConnectionClosed, allowing _run() to reconnect.
            self._outbox_event.set()
