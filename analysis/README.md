# Interhuman Analysis Plugin for Vision Agents

Post-processing upload analysis for the [Interhuman](https://docs.interhuman.ai/) API.

> **Status:** scaffold only. Implementation pending.

This package will wrap `POST /v1/upload/analyze` for offline / batch analysis
of recorded sessions: upload an MP4/WebM/MOV/etc., get back engagement state,
social signals, and (optionally) conversation quality scores.

For real-time analysis on a live call, use
[`vision-agents-plugins-interhuman-streaming`](../streaming/) instead.

## Planned API

```python
from vision_agents.plugins.interhuman_analysis import AnalysisClient

client = AnalysisClient(key_id=..., key_secret=...)
result = await client.analyze(
    "session.mp4",
    include=["conversation_quality_overall", "conversation_quality_timeline"],
)
for signal in result.signals:
    print(signal.type, signal.probability, signal.rationale)
```

## Links

- [Interhuman docs](https://docs.interhuman.ai/)
- [Upload analyze reference](https://docs.interhuman.ai/api-reference/upload-analyze)
