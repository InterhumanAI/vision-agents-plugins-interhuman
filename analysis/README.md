# Interhuman Analysis Plugin for Vision Agents

Post-processing upload analysis using the [Interhuman](https://docs.interhuman.ai/) `POST /v1/upload/analyze` API: send a recorded clip, get back engagement state, social signals, and (optionally) conversation quality scores.

For real-time analysis on a live call, use [`vision-agents-plugins-interhuman-streaming`](../streaming/) instead.

## Installation

```bash
uv add vision-agents-plugins-interhuman-analysis
```

You also need an Interhuman API key. Create one at [platform.interhuman.ai](https://platform.interhuman.ai/) and export it:

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

You can also pass raw bytes instead of a path:

```python
with open("session.mp4", "rb") as fh:
    result = await client.analyze(fh.read())
```

## Input requirements

- Formats: `mp4`, `mov`, `webm`, `mkv`, `avi`, `mpeg-ts`
- Size: 10 KB – 32 MB
- Duration: at least ~3 seconds
- One subject per video (Interhuman analyzes a single subject at a time)

## Result types

| Field | Type | Notes |
| --- | --- | --- |
| `signals` | `list[Signal]` | Twelve types: `agreement`, `confidence`, `confusion`, `disagreement`, `disengagement`, `engagement`, `frustration`, `hesitation`, `interest`, `skepticism`, `stress`, `uncertainty`. Each has `start`, `end`, `probability` (`high` / `medium` / `low`), and a short `rationale`. |
| `engagement_state` | `list[EngagementWindow]` | Per-window state: `engaged`, `neutral`, `disengaged`. |
| `conversation_quality` | `ConversationQuality \| None` | `None` unless requested via `include`. Contains an `overall` aggregate and a `timeline` of per-window scores (CQI plus clarity, authority, energy, rapport, learning). |
| `correlation_id` | `str` | Server-issued ID for support and log correlation. |

## Configuration

| Argument | Default | Notes |
| --- | --- | --- |
| `api_key` | `None` | Falls back to `INTERHUMAN_API_KEY`. |
| `base_url` | `https://api.interhuman.ai` | Override for staging environments. |
| `timeout` | `300.0` | Per-request timeout in seconds. The endpoint is synchronous and large clips can take 1–3 minutes. |

`analyze()` accepts:

| Argument | Notes |
| --- | --- |
| `file` | `str`, `pathlib.Path`, or `bytes`. |
| `include` | List of optional flags: `conversation_quality_overall`, `conversation_quality_timeline`. |
| `client_request_id` | Sent as `X-Client-Request-Id` for log correlation. |

## Errors

The client raises `InterhumanError` for any structured error response from the API:

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
