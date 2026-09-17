# Mobile tracking plan (generated)

Source: events.json. Presence is not task success. Existing SDK provenance/identity is unchanged.

| API | Wire name | Properties | Status | Consumers |
| --- | --- | --- | --- | --- |
| onboardingCompleted | Onboarding Completed | none | active | mobile-instrumentation-presence |
| phoneMicRecordingStarted | Phone Mic Recording Started | none | active | mobile-instrumentation-presence |
| phoneMicRecordingStopped | Phone Mic Recording Stopped | none | active | mobile-instrumentation-presence |
| transcribeLaterToggled | Transcribe Later Toggled | enabled | active | mobile-instrumentation-presence |
| deviceOnboardingCompleted | Device Onboarding Completed | none | active | mobile-instrumentation-presence |
| transcribeLaterRecordingProcessed | Transcribe Later Recording Processed | none | active | mobile-instrumentation-presence |
| calendarEnabled | Calendar Enabled | none | active | mobile-instrumentation-presence |
| calendarDisabled | Calendar Disabled | none | active | mobile-instrumentation-presence |
| calendarSelected | Calendar Selected | none | active | mobile-instrumentation-presence |
| conversationDisplaySettingsOpened | Conversation Display Settings Opened | none | active | mobile-instrumentation-presence |
| developerModeEnabled | Developer Mode Enabled | none | active | mobile-instrumentation-presence |
| developerModeDisabled | Developer Mode Disabled | none | active | mobile-instrumentation-presence |
| developerSettingsSaved | Developer Settings Saved | has_webhook_memory_created, has_webhook_transcript_received | active | mobile-instrumentation-presence |
| voiceResponseToggled | Voice Response Audio Toggled | enabled | active | mobile-instrumentation-presence |
| showShortConversationsToggled | Show Short Conversations Toggled | show_short | active | mobile-instrumentation-presence |
| typeExtensionProbe | Type Extension Probe | enabled, count, mode | active | c8-type-extension |
