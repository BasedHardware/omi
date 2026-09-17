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
    'Show Short Conversations Toggled',
    'Device Onboarding Abandoned',
    'Device Onboarding Double Tap Configured',
    'Phone Call Ended',
    'Short Conversation Threshold Changed',
    'Fact Search Cleared',
    'All Facts Deleted',
    'Notification Frequency Changed',
    'Changelog Dismissed',
    'Apps Filter Rating',
    'AI App Generator Prompt Submitted',
    'Voice Response Mode Changed',
    'All Facts Visibility Changed'
  )
GROUP BY event ORDER BY event;
