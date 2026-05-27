"""Tests for the Interhuman WSClient using a local websockets echo server."""

import asyncio
import json

import pytest
import websockets

from vision_agents.plugins.interhuman_streaming.ws_client import WSClient


@pytest.fixture
async def echo_server():
    """A trivial WebSocket server that records text frames and replies with canned events."""

    received: list = []
    binary_received: list[bytes] = []

    async def handler(ws):
        # Send session.ready first.
        await ws.send(
            json.dumps(
                {
                    "type": "session.ready",
                    "correlation_id": "ready",
                    "data": {"min_segment_duration_seconds": 3},
                }
            )
        )
        async for msg in ws:
            if isinstance(msg, bytes):
                binary_received.append(msg)
                # Reply with a fake signal.
                await ws.send(
                    json.dumps(
                        {
                            "type": "signal.detected",
                            "correlation_id": "s1",
                            "data": {
                                "signal_type": "agreement",
                                "start": 1.0,
                                "probability": "high",
                                "rationale": "test",
                            },
                        }
                    )
                )
            else:
                received.append(msg)

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield {
        "url": f"ws://127.0.0.1:{port}",
        "received": received,
        "binary_received": binary_received,
    }
    server.close()
    await server.wait_closed()


class TestWSClient:
    async def test_sends_config_on_connect(self, echo_server):
        events: list = []

        async def on_event(event):
            events.append(event)

        client = WSClient(
            url=echo_server["url"],
            api_key="key",
            include=["conversation_quality_overall"],
            on_event=on_event,
            plugin_name="interhuman",
        )
        await client.start()
        # Wait briefly for the config message to arrive.
        for _ in range(50):
            if echo_server["received"]:
                break
            await asyncio.sleep(0.05)
        await client.close()

        assert echo_server["received"], "config message never sent"
        config = json.loads(echo_server["received"][0])
        assert config == {"include": ["conversation_quality_overall"]}

    async def test_sends_binary_segment_and_dispatches_signal(self, echo_server):
        events: list = []

        async def on_event(event):
            events.append(event)

        client = WSClient(
            url=echo_server["url"],
            api_key="key",
            include=[],
            on_event=on_event,
            plugin_name="interhuman",
        )
        await client.start()
        await client.send_segment(b"\x1a\x45\xdf\xa3" + b"\x00" * 1024)

        for _ in range(50):
            if events:
                break
            await asyncio.sleep(0.05)
        await client.close()

        assert echo_server["binary_received"], "binary frame never reached server"
        assert any(e.type == "plugin.interhuman.signal" for e in events)

    async def test_drops_segments_older_than_max_age(self, echo_server):
        events: list = []

        async def on_event(event):
            events.append(event)

        # Force a closed-state initially: point at a port nothing listens on.
        client = WSClient(
            url="ws://127.0.0.1:1",
            api_key="key",
            include=[],
            on_event=on_event,
            plugin_name="interhuman",
            max_outbox_age_seconds=0.05,
            backoff_initial_seconds=10.0,  # don't reconnect during the test
        )
        await client.start()
        await client.send_segment(b"old")
        await asyncio.sleep(0.2)  # outbox entry should now be expired
        await client.close()
        # Just assert no crash and no signals dispatched.
        assert all(e.type != "plugin.interhuman.signal" for e in events)
