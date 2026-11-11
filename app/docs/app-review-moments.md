# Mobile store review moments

The iOS and Android app may request the native review sheet after a nonempty daily recap or a completed, non-discarded conversation summary is read. It never asks for sentiment first, gates on survey answers, offers rewards, or navigates to a store. The OS may decline to show a sheet; an API return does not prove a view or rating.

## Policy (2026-09-29)

- Require five seconds of visible, foreground, idle reading, followed by a two-second pause at the bottom. Scrollable pages require a real user scroll. The existing navigation, tab, editing, sharing, playback, onboarding, signed-out, call, phone-recording, and background cancellation checks remain.
- No account-age or reading-day gate. Ignore legacy `has_shown_review_prompt` flags; they carry no reliable attempt date. PostHog's last 14 days showed zero `eligible` decisions and zero attempts: about 60% of opportunities were `not_familiar`, about 40% `migration_cooldown`.
- At most one native attempt per marketing version, three per rolling 365 days, one per process, and 30 days between attempts. The 30-day spacing gives new versions room within days while the yearly and version limits remain hard caps. Reserve an attempt persistently before the native call; storage errors fail closed.
- Suppress for three days after a saved negative chat message rating, a visible recording upload/transcription failure, or a locally caught crash/fatal error. Store only the latest timestamp in each category on this install. The suppression is shared across both reading moments and local account switches.
- The runtime PostHog flag `mobile_store_review_tuning` may supply integer `reading_seconds` (1–30) and `cooldown_days` (1–365). Defaults are five seconds and 30 days if the flag, payload, analytics identity, or consent is unavailable. The yearly and version caps are never remotely relaxed.

Local app storage may reset on reinstall. Native store quotas remain independent. Telemetry reports closed opportunity decisions, request attempts, and API outcomes; it contains no reading content, feedback text, or rating and makes no claim that a review appeared.
