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
| memoriesPageEditedMemory | Fact Page Edited Fact | none | active | mobile-instrumentation-presence |
| memoriesPageCreateMemoryBtn | Fact Page Create Fact Button Pressed | none | active | mobile-instrumentation-presence |
| memoriesManagementSheetOpened | Facts Management Sheet Opened | none | active | mobile-instrumentation-presence |
| conversationMergeSelectionModeEntered | Conversation Merge Selection Mode Entered | none | active | mobile-instrumentation-presence |
| conversationMergeSelectionModeExited | Conversation Merge Selection Mode Exited | none | active | mobile-instrumentation-presence |
| addManualConversationClicked | Add Manual Memory Clicked | none | active | mobile-instrumentation-presence |
| userIDCopied | User ID Copied | none | active | mobile-instrumentation-presence |
| exportMemories | Dev Mode Export Memories | none | active | mobile-instrumentation-presence |
| importMemories | Dev Mode Import Memories | none | active | mobile-instrumentation-presence |
| importedMemories | Dev Mode Imported Memories | none | active | mobile-instrumentation-presence |
| supportContacted | Support Contacted | none | active | mobile-instrumentation-presence |
| upgradeSucceeded | Upgrade Succeeded | none | active | mobile-instrumentation-presence |
| upgradeCancelled | Upgrade Cancelled | none | active | mobile-instrumentation-presence |
| upgradeModalDismissed | Upgrade Modal Dismissed | none | active | mobile-instrumentation-presence |
| upgradeModalClicked | Upgrade Modal Clicked | none | active | mobile-instrumentation-presence |
| subscriptionCancelFlowStarted | Subscription Cancel Flow Started | none | active | mobile-instrumentation-presence |
| connectFriendClicked | Connect Friend Clicked | none | active | mobile-instrumentation-presence |
| disconnectFriendClicked | Disconnect Friend Clicked | none | active | mobile-instrumentation-presence |
| batteryIndicatorClicked | Battery Indicator Clicked | none | active | mobile-instrumentation-presence |
| addedPerson | Added Person | none | active | mobile-instrumentation-presence |
| removedPerson | Removed Person | none | active | mobile-instrumentation-presence |
| tagSheetOpened | Tag Sheet Opened | none | active | mobile-instrumentation-presence |
| untaggedSegment | Untagged Segment | none | active | mobile-instrumentation-presence |
| editSegmentTextStarted | Edit Segment Text Started | none | active | mobile-instrumentation-presence |
| editSegmentTextSaved | Edit Segment Text Saved | none | active | mobile-instrumentation-presence |
| editSegmentTextCancelled | Edit Segment Text Cancelled | none | active | mobile-instrumentation-presence |
| editSummaryStarted | Edit Summary Started | none | active | mobile-instrumentation-presence |
| editSummarySaved | Edit Summary Saved | none | active | mobile-instrumentation-presence |
| editSummaryCancelled | Edit Summary Cancelled | none | active | mobile-instrumentation-presence |
| deleteAccountClicked | Delete Account Clicked | none | active | mobile-instrumentation-presence |
| deleteAccountConfirmed | Delete Account Confirmed | none | active | mobile-instrumentation-presence |
| deleteAccountCancelled | Delete Account Cancelled | none | active | mobile-instrumentation-presence |
| deleteAccountFlowStarted | Delete Account Flow Started | none | active | mobile-instrumentation-presence |
| appsFilterOpened | Apps Filter Opened | none | active | mobile-instrumentation-presence |
| appsFilterApplied | Apps Filter Applied | none | active | mobile-instrumentation-presence |
| appsClearFilters | Apps Clear Filters | none | active | mobile-instrumentation-presence |
| brainMapOpened | Brain Map Opened | none | active | mobile-instrumentation-presence |
| brainMapShareClicked | Brain Map Share Clicked | none | active | mobile-instrumentation-presence |
| actionItemsPageOpened | Action Items Page Opened | none | active | mobile-instrumentation-presence |
| actionItemsDateFilterCleared | Action Items Date Filter Cleared | none | active | mobile-instrumentation-presence |
| trainingDataOptInSubmitted | Training Data Opt-In Submitted | none | active | mobile-instrumentation-presence |
| trainingDataOptInApproved | Training Data Opt-In Approved | none | active | mobile-instrumentation-presence |
| calendarFilterCleared | Calendar Filter Cleared | none | active | mobile-instrumentation-presence |
| searchBarFocused | Search Bar Focused | none | active | mobile-instrumentation-presence |
| searchQueryCleared | Search Query Cleared | none | active | mobile-instrumentation-presence |
| exportTasksBannerClicked | Export Tasks Banner Clicked | none | active | mobile-instrumentation-presence |
| createFolderButtonClicked | Create Folder Button Clicked | none | active | mobile-instrumentation-presence |
| wrappedPageOpened | Wrapped Page Opened | none | active | mobile-instrumentation-presence |
| wrappedBannerClicked | Wrapped Banner Clicked | none | active | mobile-instrumentation-presence |
| wrappedGenerationStarted | Wrapped Generation Started | none | active | mobile-instrumentation-presence |
| dailySummarySettingsOpened | Daily Summary Settings Opened | none | active | mobile-instrumentation-presence |
| permissionsSettingsOpened | Permissions Settings Opened | none | active | mobile-instrumentation-presence |
| permissionsInterstitialShown | Permissions Interstitial Shown | none | active | mobile-instrumentation-presence |
| permissionsInterstitialCompleted | Permissions Interstitial Completed | none | active | mobile-instrumentation-presence |
| permissionsInterstitialSkipped | Permissions Interstitial Skipped | none | active | mobile-instrumentation-presence |
| recapTabOpened | Recap Tab Opened | none | active | mobile-instrumentation-presence |
| whatsNewOpened | Whats New Opened | none | active | mobile-instrumentation-presence |
| dailyScoreHelpTapped | Daily Score Help Tapped | none | active | mobile-instrumentation-presence |
| integrationsPageOpened | Integrations Page Opened | none | active | mobile-instrumentation-presence |
| paymentsPageOpened | Payments Page Opened | none | active | mobile-instrumentation-presence |
| connectDevicePageOpened | Connect Device Page Opened | none | active | mobile-instrumentation-presence |
| getOmiDeviceClicked | Get Omi Device Clicked | none | active | mobile-instrumentation-presence |
| connectionGuideOpened | Connection Guide Opened | none | active | mobile-instrumentation-presence |
| dataPrivacyPageOpened | Data Privacy Page Opened | none | active | mobile-instrumentation-presence |
| aiAppGeneratorPageOpened | AI App Generator Page Opened | none | active | mobile-instrumentation-presence |
| importHistoryPageOpened | Import History Page Opened | none | active | mobile-instrumentation-presence |
| liveTranscriptCardClicked | Live Transcript Card Clicked | has_segments, has_photos, segment_count, photo_count | active | mobile-instrumentation-presence |
| appleRemindersSyncCompleted | Apple Reminders Sync Completed | pending_exported, synced_checked, completions_pulled, completions_pushed, title_due_pulled, title_due_pushed, reminders_unlinked | active | mobile-instrumentation-presence |
| wrappedGenerationCompleted | Wrapped Generation Completed | total_conversations, total_minutes, days_active | active | mobile-instrumentation-presence |
| typeExtensionProbe | Type Extension Probe | enabled, count, mode | active | c8-type-extension |
