"""Typed events emitted by the Interhuman plugin."""

from dataclasses import dataclass, field
from typing import Literal, Optional

from vision_agents.core.events import PluginBaseEvent


@dataclass
class ConversationQualityScores:
    """Five-dimension behavioral quality scores plus the aggregated CQI."""

    quality_index: int = 0
    clarity: int = 0
    authority: int = 0
    energy: int = 0
    rapport: int = 0
    learning: int = 0


@dataclass
class ConversationQualityWindow:
    """Time-bounded conversation quality scores."""

    start: float
    end: float
    values: ConversationQualityScores


@dataclass
class InterhumanSignalEvent(PluginBaseEvent):
    """Emitted on signal.detected, signal.updated, and signal.ended."""

    type: str = field(default="plugin.interhuman.signal", init=False)
    phase: Literal["detected", "updated", "ended"] = "detected"
    signal_type: str = ""
    start: float = 0.0
    end: Optional[float] = None
    probability: Optional[Literal["high", "medium", "low"]] = None
    rationale: str = ""
    correlation_id: str = ""


@dataclass
class InterhumanEngagementEvent(PluginBaseEvent):
    """Engagement state change emitted by the Interhuman backend."""

    type: str = field(default="plugin.interhuman.engagement", init=False)
    state: Literal["engaged", "neutral", "disengaged"] = "neutral"
    start: float = 0.0
    correlation_id: str = ""


@dataclass
class InterhumanConversationQualityEvent(PluginBaseEvent):
    """Per-cadence conversation quality update."""

    type: str = field(default="plugin.interhuman.conversation_quality", init=False)
    overall: Optional[ConversationQualityScores] = None
    timeline: list[ConversationQualityWindow] = field(default_factory=list)
    correlation_id: str = ""


@dataclass
class InterhumanRawEvent(PluginBaseEvent):
    """Forward-compat raw server payload for unknown or pass-through events."""

    type: str = field(default="plugin.interhuman.raw", init=False)
    payload: dict = field(default_factory=dict)
