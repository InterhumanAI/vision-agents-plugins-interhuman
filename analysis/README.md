# Interhuman Analysis Plugin for Vision Agents

Analyze recorded conversations for social signals, engagement patterns, and conversation quality. Send a video file, get back timestamped behavioral insights — who showed confusion at 0:42, when engagement dropped, and an overall quality score.

For real-time analysis during a live call, use [`interhuman-streaming`](../streaming/) instead.

## Installation

```bash
uv add vision-agents-plugins-interhuman-analysis
```

You need an Interhuman API key. Create one at [platform.interhuman.ai](https://platform.interhuman.ai/) and export it:

```bash
export INTERHUMAN_API_KEY=...
```

## Quick start

```python
from vision_agents.plugins.interhuman_analysis import AnalysisClient

client = AnalysisClient()  # reads INTERHUMAN_API_KEY from env

result = await client.analyze(
    "session.mp4",
    include=["conversation_quality_overall", "conversation_quality_timeline"],
)

for signal in result.signals:
    print(signal.start, signal.signal_type, signal.probability, signal.rationale)

for window in result.engagement_state:
    print(window.start, window.end, window.state)

if result.conversation_quality and result.conversation_quality.overall:
    print("CQI:", result.conversation_quality.overall.quality_index)
```

You can also pass raw bytes:

```python
with open("session.mp4", "rb") as fh:
    result = await client.analyze(fh.read())
```

## What you get back

| Field | Type | Description |
| --- | --- | --- |
| `signals` | `list[Signal]` | 10 signal types (agreement, confusion, hesitation, frustration, etc.) each with `start`, `end`, `probability`, and a human-readable `rationale`. |
| `engagement_state` | `list[EngagementWindow]` | Per-window state: `engaged`, `neutral`, `disengaged`. |
| `conversation_quality` | `ConversationQuality \| None` | Overall CQI (0–100) plus five dimension scores: clarity, authority, energy, rapport, learning. Also available as a timeline of per-window scores. Only returned when requested via `include`. |
| `correlation_id` | `str` | Server-issued ID for support and log correlation. |

## Input requirements

- Formats: `mp4`, `mov`, `webm`, `mkv`, `avi`, `mpeg-ts`
- Size: 10 KB – 32 MB
- Duration: at least ~3 seconds
- One subject per video (Interhuman analyzes a single subject at a time)

## Configuration

| Argument | Default | Notes |
| --- | --- | --- |
| `api_key` | `None` | Falls back to `INTERHUMAN_API_KEY`. |
| `base_url` | `https://api.interhuman.ai` | Override for staging environments. |
| `timeout` | `300.0` | Per-request timeout in seconds. Large clips can take 1–3 minutes. |

`analyze()` accepts:

| Argument | Notes |
| --- | --- |
| `file` | `str`, `pathlib.Path`, or `bytes`. |
| `include` | List of optional flags: `conversation_quality_overall`, `conversation_quality_timeline`. |
| `client_request_id` | Sent as `X-Client-Request-Id` for log correlation. |

## Errors

```python
from vision_agents.plugins.interhuman_analysis import AnalysisClient, InterhumanError

try:
    result = await client.analyze("clip.mp4")
except InterhumanError as err:
    print(err.status_code, err.error_id, err.correlation_id, err.link)
```

Network-level failures surface as `httpx.HTTPError` subclasses.

## Development

```bash
git clone https://github.com/InterhumanAI/vision-agents-plugins-interhuman
cd vision-agents-plugins-interhuman
uv sync --dev

# unit tests
uv run --no-sync pytest analysis -m "not integration"

# lint + types
uv run --no-sync ruff check .
uv run --no-sync mypy
```

## Links

- [Interhuman docs](https://docs.interhuman.ai/)
- [Upload analyze reference](https://docs.interhuman.ai/api-reference/upload-analyze)
- [Vision Agents docs](https://visionagents.ai/)
- [Vision Agents repo](https://github.com/GetStream/vision-agents)
