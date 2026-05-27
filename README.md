# Interhuman Plugins for Vision Agents

[Vision Agents](https://visionagents.ai/) plugins that wrap the
[Interhuman](https://docs.interhuman.ai/) social-intelligence API.

This repo is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/)
with two independently-versioned PyPI packages:

| Package | Path | Purpose |
| --- | --- | --- |
| [`vision-agents-plugins-interhuman-streaming`](streaming/) | `streaming/` | Real-time streaming of a live call to `wss://api.interhuman.ai/v1/stream/analyze`, emitting typed signal / engagement / conversation-quality events on the agent bus. |
| [`vision-agents-plugins-interhuman-analysis`](analysis/) | `analysis/` | *(scaffold)* Post-processing upload analysis via `POST /v1/upload/analyze` for recorded sessions. |

## Choosing a package

- **Live conversation, react in real time** → `streaming`.
- **Analyze a recorded video offline** → `analysis`.

You can install both side by side; they share no runtime code.

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
