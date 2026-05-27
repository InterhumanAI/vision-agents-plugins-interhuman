"""Tests for parsing Interhuman server JSON into typed events."""

from vision_agents.plugins.interhuman.events import (
    ConversationQualityScores,
    ConversationQualityWindow,
    InterhumanConversationQualityEvent,
    InterhumanEngagementEvent,
    InterhumanRawEvent,
    InterhumanSignalEvent,
)
from vision_agents.plugins.interhuman.ws_client import parse_server_event


class TestParseServerEvent:
    def test_signal_detected(self):
        msg = {
            "type": "signal.detected",
            "correlation_id": "abc",
            "data": {
                "signal_type": "agreement",
                "start": 3.0,
                "probability": "high",
                "rationale": "Subject nodded.",
            },
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        assert any(isinstance(e, InterhumanSignalEvent) for e in events)
        signal = next(e for e in events if isinstance(e, InterhumanSignalEvent))
        assert signal.phase == "detected"
        assert signal.signal_type == "agreement"
        assert signal.start == 3.0
        assert signal.probability == "high"
        assert signal.rationale == "Subject nodded."
        assert signal.correlation_id == "abc"

    def test_signal_updated(self):
        msg = {
            "type": "signal.updated",
            "correlation_id": "abc",
            "data": {
                "signal_type": "agreement",
                "start": 6.0,
                "probability": "medium",
                "rationale": "Looked away.",
            },
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        signal = next(e for e in events if isinstance(e, InterhumanSignalEvent))
        assert signal.phase == "updated"

    def test_signal_ended(self):
        msg = {
            "type": "signal.ended",
            "correlation_id": "abc",
            "data": {"signal_type": "agreement", "end": 14.0},
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        signal = next(e for e in events if isinstance(e, InterhumanSignalEvent))
        assert signal.phase == "ended"
        assert signal.signal_type == "agreement"
        assert signal.end == 14.0

    def test_engagement_updated(self):
        msg = {
            "type": "engagement.updated",
            "correlation_id": "xyz",
            "data": {"state": "engaged", "start": 42.0},
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        engagement = next(e for e in events if isinstance(e, InterhumanEngagementEvent))
        assert engagement.state == "engaged"
        assert engagement.start == 42.0
        assert engagement.correlation_id == "xyz"

    def test_conversation_quality_overall_only(self):
        msg = {
            "type": "conversation_quality.updated",
            "correlation_id": "q1",
            "data": {
                "overall": {
                    "quality_index": 72,
                    "clarity": 67,
                    "authority": 68,
                    "energy": 80,
                    "rapport": 75,
                    "learning": 70,
                }
            },
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        quality = next(
            e for e in events if isinstance(e, InterhumanConversationQualityEvent)
        )
        assert quality.overall == ConversationQualityScores(
            quality_index=72,
            clarity=67,
            authority=68,
            energy=80,
            rapport=75,
            learning=70,
        )
        assert quality.timeline == []

    def test_conversation_quality_timeline(self):
        msg = {
            "type": "conversation_quality.updated",
            "correlation_id": "q1",
            "data": {
                "timeline": [
                    {
                        "start": 0,
                        "end": 11,
                        "values": {
                            "quality_index": 70,
                            "clarity": 69,
                            "authority": 70,
                            "energy": 78,
                            "rapport": 77,
                            "learning": 68,
                        },
                    }
                ]
            },
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        quality = next(
            e for e in events if isinstance(e, InterhumanConversationQualityEvent)
        )
        assert quality.overall is None
        assert len(quality.timeline) == 1
        assert quality.timeline[0] == ConversationQualityWindow(
            start=0,
            end=11,
            values=ConversationQualityScores(
                quality_index=70,
                clarity=69,
                authority=70,
                energy=78,
                rapport=77,
                learning=68,
            ),
        )

    def test_conversation_quality_null_timeline(self):
        msg = {
            "type": "conversation_quality.updated",
            "correlation_id": "q2",
            "data": {"overall": None, "timeline": None},
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        quality = next(
            e for e in events if isinstance(e, InterhumanConversationQualityEvent)
        )
        assert quality.overall is None
        assert quality.timeline == []

    def test_session_ready_emits_no_public_event(self):
        msg = {
            "type": "session.ready",
            "correlation_id": "sr",
            "data": {"min_segment_duration_seconds": 3},
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        assert events == []

    def test_session_updated_emits_no_public_event(self):
        msg = {"type": "session.updated", "correlation_id": "su", "data": {}}
        events = parse_server_event(msg, plugin_name="interhuman")
        assert events == []

    def test_error_emits_raw_event(self):
        msg = {
            "type": "error",
            "correlation_id": "err1",
            "data": {"code": "ih6002", "message": "too large", "segment": 2},
        }
        events = parse_server_event(msg, plugin_name="interhuman")
        raw = next(e for e in events if isinstance(e, InterhumanRawEvent))
        assert raw.payload == msg

    def test_unknown_type_emits_raw_event(self):
        msg = {"type": "future.event", "correlation_id": "f", "data": {"x": 1}}
        events = parse_server_event(msg, plugin_name="interhuman")
        raw = next(e for e in events if isinstance(e, InterhumanRawEvent))
        assert raw.payload == msg
