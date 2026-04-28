# Ambient Capture Plugin Controller

Controller plugins should expose a policy endpoint returning signed policy JSON. Ed25519 signatures are preferred. The Omi app verifies the policy locally before applying it.

Required policy fields include:

- `plugin_id`
- `scope: ambient_capture_controller`
- `user_id`
- `device_id`
- `sequence`
- `issued_at`
- `valid_until`
- `capture_mode`
- upload and fallback allow flags
- communication mode
- high-risk app list

Telemetry is sent only when the user enables plugin telemetry/control. It must not include raw audio or transcript text unless a future explicit user setting allows it.

Fallback text segments are labeled by source, such as `accessibility_caption`, `live_caption`, `local_stt`, `manual_note`, or `gap_marker`. They must not be silently blended into normal audio-derived transcripts.
