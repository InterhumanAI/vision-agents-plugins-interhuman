"""Interhuman plugin for Vision Agents.

Real-time social-signal, engagement, and conversation-quality analysis using
the Interhuman streaming API.
"""

from vision_agents.plugins.interhuman.events import (
    ConversationQualityScores,
    ConversationQualityWindow,
    InterhumanConversationQualityEvent,
    InterhumanEngagementEvent,
    InterhumanRawEvent,
    InterhumanSignalEvent,
)
from vision_agents.plugins.interhuman.processor import InterhumanProcessor

__all__ = [
    "ConversationQualityScores",
    "ConversationQualityWindow",
    "InterhumanConversationQualityEvent",
    "InterhumanEngagementEvent",
    "InterhumanProcessor",
    "InterhumanRawEvent",
    "InterhumanSignalEvent",
]
