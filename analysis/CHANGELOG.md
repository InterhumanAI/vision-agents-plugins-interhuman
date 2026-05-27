# Changelog

## 0.1.0

Initial release of `vision-agents-plugins-interhuman-analysis`.

- `AnalysisClient.analyze(file, *, include=None, client_request_id=None)` wraps `POST /v1/upload/analyze`.
- Accepts `str`, `pathlib.Path`, or `bytes` for the upload.
- Returns a typed `AnalysisResult` with `signals`, `engagement_state`, optional `conversation_quality` (overall + timeline), and `correlation_id`.
- Raises `InterhumanError` with `status_code`, `error_id`, `correlation_id`, and `link` on structured API errors.
