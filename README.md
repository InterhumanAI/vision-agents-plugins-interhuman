# Interhuman Plugins for Vision Agents

Social intelligence for your Vision Agents — detect behavioral signals, track engagement, and score conversation quality from video and audio in real time or post-session. Make agents that read the room.

[Interhuman](https://docs.interhuman.ai/) analyzes how people communicate: hesitation, confusion, agreement, frustration, and 10 other observable behaviors across voice, facial expressions, and body language. These plugins wire that capability into any [Vision Agents](https://visionagents.ai/) agent.

## Packages

This repo is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) with two independently-versioned PyPI packages:

| Package | Install | Use when |
| --- | --- | --- |
| [`interhuman-streaming`](streaming/) | `uv add vision-agents-plugins-interhuman-streaming` | Live call — react to signals as they happen |
| [`interhuman-analysis`](analysis/) | `uv add vision-agents-plugins-interhuman-analysis` | Recorded video — analyze a session after the fact |

Both share no runtime code and can be installed side by side.

## What you can build

- **Adaptive AI tutors** that slow down when a student shows confusion and accelerate on agreement
- **Interview and sales coaching** that scores communication quality (clarity, authority, energy, rapport) live
- **Empathetic support agents** that detect frustration or disengagement and adjust tone in the moment
- **Conversation analytics dashboards** with per-window quality timelines and an overall CQI score (0–100)
- **Post-session reports** with timestamped behavioral insights from recorded calls

## Development

```bash
git clone https://github.com/InterhumanAI/vision-agents-plugins-interhuman
cd vision-agents-plugins-interhuman
uv sync --dev

# tests across both packages
uv run --no-sync pytest -m "not integration"

# integration tests (need INTERHUMAN_API_KEY)
uv run --no-sync pytest -m integration

# lint + types
uv run --no-sync ruff check .
uv run --no-sync mypy
```

## Links

- [Interhuman docs](https://docs.interhuman.ai/)
- [Vision Agents docs](https://visionagents.ai/)
- [API keys](https://platform.interhuman.ai/)
