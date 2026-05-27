"""Typed result objects for the Interhuman upload-analysis API."""

from dataclasses import dataclass, field
from typing import Literal, Optional


SignalType = Literal[
    "agreement",
    "confidence",
    "confusion",
    "disagreement",
    "disengagement",
    "engagement",
    "frustration",
    "hesitation",
    "interest",
    "skepticism",
    "stress",
    "uncertainty",
]
EngagementState = Literal["engaged", "neutral", "disengaged"]
Probability = Literal["high", "medium", "low"]


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
class ConversationQuality:
    """Aggregate plus per-window conversation quality from upload analysis."""

    overall: Optional[ConversationQualityScores] = None
    timeline: list[ConversationQualityWindow] = field(default_factory=list)


@dataclass
class Signal:
    """A single detected social signal."""

    signal_type: SignalType
    start: float
    end: float
    probability: Probability
    rationale: str = ""


@dataclass
class EngagementWindow:
    """A time-bounded engagement state."""

    start: float
    end: float
    state: EngagementState


@dataclass
class AnalysisResult:
    """Complete Interhuman upload analysis response."""

    signals: list[Signal] = field(default_factory=list)
    engagement_state: list[EngagementWindow] = field(default_factory=list)
    conversation_quality: Optional[ConversationQuality] = None
    correlation_id: str = ""
