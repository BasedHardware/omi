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
| deviceOnboardingAbandoned | Device Onboarding Abandoned | step | active | mobile-instrumentation-presence |
| deviceOnboardingDoubleTapConfigured | Device Onboarding Double Tap Configured | action | active | mobile-instrumentation-presence |
| phoneCallEnded | Phone Call Ended | duration_seconds | active | mobile-instrumentation-presence |
| shortConversationThresholdChanged | Short Conversation Threshold Changed | threshold_seconds, threshold_minutes | active | mobile-instrumentation-presence |
| memorySearchCleared | Fact Search Cleared | total_facts_count | active | mobile-instrumentation-presence |
| memoriesAllDeleted | All Facts Deleted | facts_count_before_deletion | active | mobile-instrumentation-presence |
| notificationFrequencyChanged | Notification Frequency Changed | old_frequency, new_frequency | active | mobile-instrumentation-presence |
| changelogDismissed | Changelog Dismissed | changelog_count | active | mobile-instrumentation-presence |
| appsFilterRating | Apps Filter Rating | rating | active | mobile-instrumentation-presence |
| aiAppGeneratorPromptSubmitted | AI App Generator Prompt Submitted | prompt_length | active | mobile-instrumentation-presence |
| voiceResponseModeChanged | Voice Response Mode Changed | mode, mode_int | active | mobile-instrumentation-presence |
| memoriesAllVisibilityChanged | All Facts Visibility Changed | new_visibility, facts_count | active | mobile-instrumentation-presence |
| showDiscardedMemoriesToggled | Show Discarded Memories Toggled | show_discarded | active | mobile-instrumentation-presence |
| showDiscardedConversationsToggled | Show Discarded Conversations Toggled | show_discarded | active | mobile-instrumentation-presence |
| deletedConversationsFilterToggled | Deleted Conversations Filter Toggled | show_deleted | active | mobile-instrumentation-presence |
| appsFilterMyApps | Apps Filter My Apps | enabled | active | mobile-instrumentation-presence |
| appsFilterInstalled | Apps Filter Installed | enabled | active | mobile-instrumentation-presence |
| dailySummaryToggled | Daily Summary Toggled | enabled | active | mobile-instrumentation-presence |
| aiAppGeneratorAppGenerated | AI App Generator App Generated | success | active | mobile-instrumentation-presence |
| actionItemsViewToggled | Action Items View Toggled | grouped_view | active | mobile-instrumentation-presence |
| phoneCallStarted | Phone Call Started | has_contact_name | active | mobile-instrumentation-presence |
| phoneCallPageOpened | Phone Call Page Opened | none | active | mobile-instrumentation-presence |
| phoneCallVerificationStarted | Phone Call Verification Started | none | active | mobile-instrumentation-presence |
| phoneCallVerificationCompleted | Phone Call Verification Completed | none | active | mobile-instrumentation-presence |
| phoneCallConnected | Phone Call Connected | none | active | mobile-instrumentation-presence |
| phoneCallDialpadOpened | Phone Call Dialpad Opened | none | active | mobile-instrumentation-presence |
| phoneCallUpsellUpgradeTapped | Phone Call Upsell Upgrade Tapped | none | active | mobile-instrumentation-presence |
| phoneCallUpsellDismissed | Phone Call Upsell Dismissed | none | active | mobile-instrumentation-presence |
| deviceDisconnected | Device Disconnected | none | active | mobile-instrumentation-presence |
| speechProfileCapturePageClicked | Speech Profile Capture Page Clicked | none | active | mobile-instrumentation-presence |
| speechProfileSkipped | Speech Profile Skipped | none | active | mobile-instrumentation-presence |
| speechProfileUploadSucceeded | Speech Profile Upload Succeeded | none | active | mobile-instrumentation-presence |
| speechProfileEmbeddingStored | Speech Profile Embedding Stored | none | active | mobile-instrumentation-presence |
| speechProfileContinued | Onboarding Step Speech Profile Continued | none | active | mobile-instrumentation-presence |
| useWithoutDeviceOnboardingWelcome | Use Without Device Onboarding Welcome | none | active | mobile-instrumentation-presence |
| useWithoutDeviceOnboardingFindDevices | Use Without Device Onboarding Find Devices | none | active | mobile-instrumentation-presence |
| typeExtensionProbe | Type Extension Probe | enabled, count, mode | active | c8-type-extension |
