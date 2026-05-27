# Interhuman Plugin for Vision Agents

Real-time social-signal, engagement, and conversation-quality analysis for Vision Agents using the [Interhuman](https://docs.interhuman.ai/) streaming API.

## Installation

```bash
uv add "vision-agents[interhuman]"
# or
uv add vision-agents-plugins-interhuman
```

You also need an Interhuman API key. Create one at [platform.interhuman.ai](https://platform.interhuman.ai/) and export it:

```bash
export INTERHUMAN_API_KEY=...
```

## Quick start

```python
from vision_agents.core import Agent
from vision_agents.plugins import interhuman

processor = interhuman.InterhumanProcessor(
    include=[
        "conversation_quality_overall",
        "conversation_quality_timeline",
    ],
    window_seconds=5.0,
)

agent = Agent(processors=[processor], ...)

@agent.events.subscribe
async def on_signal(event: interhuman.InterhumanSignalEvent) -> None:
    if event.phase == "detected" and event.signal_type == "confusion":
        # The user looks confused — slow down.
        ...

@agent.events.subscribe
async def on_engagement(event: interhuman.InterhumanEngagementEvent) -> None:
    print(f"engagement -> {event.state} @ {event.start}s")

@agent.events.subscribe
async def on_quality(event: interhuman.InterhumanConversationQualityEvent) -> None:
    if event.overall:
        print(f"CQI: {event.overall.quality_index}")
```

## How it works

The processor subscribes to one participant's audio and video, fuses each fixed-length window into a WebM segment (VP8 + Opus), and streams it to `wss://api.interhuman.ai/v1/stream/analyze` over a single long-lived WebSocket. Server events are re-emitted on the agent's event bus.

```
participant audio → process_audio ─┐
                                    ├─ SegmentBuilder ─ flush every N s ─ WSClient ─ wss://api.interhuman.ai
participant video → process_video ─┘                                           ↑
                                                                                │
                                                          Interhuman API events ┘
                                                          → InterhumanSignalEvent
                                                          → InterhumanEngagementEvent
                                                          → InterhumanConversationQualityEvent
```

## Events

| Event | When |
| --- | --- |
| `InterhumanSignalEvent` | A social signal starts (`phase="detected"`), updates (`updated`), or ends (`ended`). Twelve signal types: `agreement`, `confidence`, `confusion`, `disagreement`, `disengagement`, `engagement`, `frustration`, `hesitation`, `interest`, `skepticism`, `stress`, `uncertainty`. |
| `InterhumanEngagementEvent` | Engagement state transitions: `engaged`, `neutral`, `disengaged`. |
| `InterhumanConversationQualityEvent` | Cumulative CQI plus per-window timeline scores (only when `include` requests them). |
| `InterhumanRawEvent` | Forward-compat fallback for any server event the plugin doesn't model yet, or for `error` payloads. |

## Configuration

| Argument | Default | Notes |
| --- | --- | --- |
| `api_key` | `None` | Falls back to `INTERHUMAN_API_KEY`. |
| `base_url` | `wss://api.interhuman.ai` | Override for staging environments. |
| `include` | `[]` | `conversation_quality_overall`, `conversation_quality_timeline`. |
| `window_seconds` | `5.0` | Range 3.0–30.0. Server enforces 3 s minimum. |
| `video_fps` | `15` | Encoder fps and forwarder rate. |
| `video_width` / `video_height` | `640` / `360` | Output resolution into VP8. |
| `video_bitrate` | `1_000_000` | VP8 target. |
| `audio_bitrate` | `64_000` | Opus target. |
| `target_participant_id` | `None` | If set, lock to a specific participant. Otherwise locks onto the first non-agent participant. |
| `max_outbox_age_seconds` | `30.0` | Drop queued segments older than this when disconnected. |

## Single-subject by design

Interhuman analyzes one subject at a time. The plugin locks onto the first non-agent participant it sees and ignores video/audio from anyone else for the rest of the session. If you want a specific participant, pass `target_participant_id`.

## Development

```bash
git clone https://github.com/InterhumanAI/vision-agents-plugins-interhuman
cd vision-agents-plugins-interhuman
uv sync --dev

# unit tests
uv run --no-sync pytest -m "not integration"

# integration tests (requires INTERHUMAN_API_KEY)
uv run --no-sync pytest -m integration

# lint + types
uv run --no-sync ruff check .
uv run --no-sync mypy
```

## Links

- [Interhuman docs](https://docs.interhuman.ai/)
- [Interhuman streaming reference](https://docs.interhuman.ai/api-reference/stream-analyze)
- [Vision Agents docs](https://visionagents.ai/)
- [Vision Agents repo](https://github.com/GetStream/vision-agents)
