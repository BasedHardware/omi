-- Offline/PostHog SQL projection: bind one namespace and build; never infer identity from person properties.
SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Onboarding Completed',
    'Phone Mic Recording Started',
    'Phone Mic Recording Stopped',
    'Transcribe Later Toggled',
    'Device Onboarding Completed',
    'Transcribe Later Recording Processed',
    'Calendar Enabled',
    'Calendar Disabled',
    'Calendar Selected',
    'Conversation Display Settings Opened',
    'Developer Mode Enabled',
    'Developer Mode Disabled',
    'Developer Settings Saved',
    'Voice Response Audio Toggled',
    'Show Short Conversations Toggled'
  )
GROUP BY event ORDER BY event;
