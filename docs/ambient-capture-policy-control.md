# Ambient Capture Policy Control

An ambient capture controller is an Omi app with the `ambient_capture_controller` capability. Only one enabled controller app can be selected per user/device.

The controller does not access Android microphone APIs directly. Omi fetches signed policy from the controller backend, verifies it locally, and applies it only if local user settings allow it.

Policies are rejected when the signature is invalid, expired, replayed, for the wrong user/device/plugin, missing the `ambient_capture_controller` scope, or when local user choices disallow the requested behavior.

Local controls are authoritative:

- Master Advanced Ambient Capture off blocks capture.
- Private Mode cannot be disabled by plugin policy.
- Accessibility mode requires both the local toggle and Android Accessibility service grant.
- Raw audio upload requires the local raw audio upload toggle.

Controller metadata lives on the app external integration:

- `capture_policy_url`
- `capture_telemetry_url`
- `fallback_segments_url`
- `capture_controller_public_key`
- `capture_controller_key_id`
- `capture_controller_scopes`
