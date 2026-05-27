# Changelog

## v0.1.0

Initial release of `vision-agents-plugins-interhuman-streaming`.

### New Features

- `InterhumanProcessor` streams a single participant's audio + video to
  `wss://api.interhuman.ai/v1/stream/analyze` in fixed-length WebM segments
  (VP8 + Opus).
- Typed events on the agent bus: `InterhumanSignalEvent`,
  `InterhumanEngagementEvent`, `InterhumanConversationQualityEvent`, plus a
  catch-all `InterhumanRawEvent`.
- `WSClient` with reconnect, exponential backoff, and a bounded outbox that
  drops segments older than `max_outbox_age_seconds` while disconnected.
- `SegmentBuilder` muxes WebM with VP8 video and Opus audio, resamples PCM
  to 48 kHz when needed, and pads short windows up to `min_segment_seconds`
  so the server doesn't reject sub-3-second segments (`ih5006`).
- Shielded server-event parsing so a single malformed payload no longer kills
  the receive loop.
