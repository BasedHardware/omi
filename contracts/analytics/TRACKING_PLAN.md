# Mobile tracking plan (generated)

Source: events.json. Presence is not task success. Existing SDK provenance/identity is unchanged.

| API | Wire name | Properties | Status | Consumers |
| --- | --- | --- | --- | --- |
| savedPendantReconnectObserved | Saved Pendant Reconnect | trigger, attempt, result, disconnected_ms | active | saved-pendant-reconnect |
| onboardingCompleted | Onboarding Completed | none | active | mobile-instrumentation-presence |
| recordingProducedNoConversation | Recording Produced No Conversation | source, duration_s, transcript_observed, reason | active | onboarding-activation-funnel |
| onboardingWelcomeShown | Onboarding Welcome Shown | none | active | onboarding-activation-funnel |
| onboardingGetStartedTapped | Onboarding Get Started Tapped | none | active | onboarding-activation-funnel |
| signInStarted | Sign In Started | provider | active | onboarding-activation-funnel |
| signInFailed | Sign In Failed | provider, error_class | active | onboarding-activation-funnel |
| onboardingPermissionResult | Onboarding Permission Result | permission, granted, permanently_denied, services_disabled | active | onboarding-activation-funnel |
| devicePairingBlocked | Device Pairing Blocked | reason, android_sdk, ios_version | active | onboarding-activation-funnel |
| deviceScanEmpty | Device Scan Empty | after_seconds | active | onboarding-activation-funnel |
| deviceConnectFailureShown | Device Connect Failure Shown | failure_reason, platform | active | onboarding-activation-funnel |
| deviceConnectFailed | Device Connect Failed | error_class | active | onboarding-activation-funnel |
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
| deviceDisconnected | Device Disconnected | none | deprecated | mobile-instrumentation-presence, connection-balance |
| deviceDisconnectedDetailed | Device Disconnected Detailed | reason, reason_code, app_state | active | mobile-instrumentation-presence, connection-balance |
| diagnosticsSent | Diagnostics Sent | bundle_bytes, disconnect_count, schema_version | active | mobile-instrumentation-presence |
| diagnosticsSendFailed | Diagnostics Send Failed | bundle_bytes, disconnect_count, schema_version, failure_stage, status_code | active | mobile-instrumentation-presence |
| speechProfileCapturePageClicked | Speech Profile Capture Page Clicked | none | active | mobile-instrumentation-presence |
| speechProfileSkipped | Speech Profile Skipped | none | active | mobile-instrumentation-presence |
| speechProfileUploadSucceeded | Speech Profile Upload Succeeded | none | active | mobile-instrumentation-presence |
| speechProfileEmbeddingStored | Speech Profile Embedding Stored | none | active | mobile-instrumentation-presence |
| speechProfileContinued | Onboarding Step Speech Profile Continued | none | active | mobile-instrumentation-presence |
| onboardingSetupRatingPromptShown | Onboarding Setup Rating Prompt Shown | none | active | mobile-instrumentation-presence |
| onboardingSetupRatingPromptAnswered | Onboarding Setup Rating Prompt Answered | answer | active | mobile-instrumentation-presence |
| firstSummaryRatingPromptShown | First Summary Rating Prompt Shown | none | active | mobile-instrumentation-presence |
| firstSummaryRatingPromptAnswered | First Summary Rating Prompt Answered | answer | active | mobile-instrumentation-presence |
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
| upgradeSucceeded | Upgrade Succeeded | none | active | mobile-instrumentation-presence, subscription-funnel |
| upgradeCancelled | Upgrade Cancelled | none | active | mobile-instrumentation-presence, subscription-funnel |
| upgradeModalDismissed | Upgrade Modal Dismissed | none | active | mobile-instrumentation-presence, app-update-prompt |
| upgradeModalClicked | Upgrade Modal Clicked | none | active | mobile-instrumentation-presence, app-update-prompt |
| subscriptionCancelFlowStarted | Subscription Cancel Flow Started | none | active | mobile-instrumentation-presence, subscription-funnel |
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
| appReviewOpportunity | App Review Opportunity | moment, decision | active | mobile-review-presence |
| appReviewRequestAttempted | App Review Request Attempted | moment | active | mobile-review-presence |
| appReviewRequestFinished | App Review Request Finished | moment, result | active | mobile-review-presence |
| productJourneyStarted | Product Journey Started | journey, surface, object_id | active | mobile-product-outcomes |
| productJourneyFirstResult | Product Journey First Result | journey, surface, object_id, duration_ms | active | mobile-product-outcomes |
| productJourneyOutcome | Product Journey Outcome | journey, surface, object_id, outcome, failure, duration_ms, result_count | active | mobile-product-outcomes |
| productValueEvent | Product Value | kind, surface, object_id | active | mobile-product-outcomes |
| conversationAction | Conversation Action | action, surface | active | mobile-conversation-actions |
| speakerTagPromptsViewed | Speaker Tag Prompts Viewed | prompt_count, first_time | active | speaker-tag-prompts-funnel |
| speakerTagPromptClipPlayed | Speaker Tag Prompt Clip Played | kind, loaded | active | speaker-tag-prompts-funnel |
| speakerTagPromptAnswerSubmitted | Speaker Tag Prompt Answer Submitted | kind, answer, clip_played, first_time, succeeded | active | speaker-tag-prompts-funnel |
| billingSubscriptionStarted | Billing Subscription Started | plan, interval, reason, price_generation, is_trial, billing_measurement, mrr_cents, $insert_id, billing_event_id, occurred_at, billing_source, price_id, currency | active | billing-lifecycle-events |
| billingSubscriptionChurned | Billing Subscription Churned | plan, interval, reason, price_generation, is_trial, billing_measurement, mrr_cents, $insert_id, billing_event_id, occurred_at, billing_source, price_id, currency | active | billing-lifecycle-events |
| billingSubscriptionCancellationScheduled | Billing Subscription Cancellation Scheduled | plan, interval, reason, price_generation, is_trial, billing_measurement, mrr_cents, $insert_id, billing_event_id, occurred_at, billing_source, price_id, currency | active | billing-lifecycle-events |
| billingSubscriptionPlanChanged | Billing Subscription Plan Changed | previous_plan, new_plan, interval, mrr_before_cents, mrr_after_cents, plan, reason, price_generation, is_trial, billing_measurement, mrr_cents, $insert_id, billing_event_id, occurred_at, billing_source, price_id, currency | active | billing-plan-changes |
| speakerTagPromptsClosed | Speaker Tag Prompts Closed | answered_count, prompt_count | active | speaker-tag-prompts-funnel |
| voiceProfileSettingToggled | Voice Profile Setting Toggled | setting, enabled, source, succeeded | active | speaker-tag-prompts-funnel |
| voiceReplyPlayback | Voice Reply Playback | outcome, skip_reason, mode, output_route, chunks_requested, chunks_played, chunks_dropped, fallback_reason, first_audio_latency_ms, interrupt_source | active | mobile-instrumentation-presence |
| pendantVoiceQuestionDropped | Pendant Voice Question Dropped | reason | active | mobile-instrumentation-presence |
| siriIntentPerformed | Siri Intent Performed | intent, platform, outcome, latency_ms, invoked_via | active | siri-intents |
| siriAskOmiPerformed | Siri Ask Omi Performed | platform, outcome, latency_ms, invoked_via | active | siri-intents |
| siriIndexRebuilt | Siri Index Rebuilt | platform, entity_counts, duration_ms, outcome | active | siri-index-health |
| conversationUntitledRendered | Conversation Untitled Rendered | surface, age_bucket, summary_retryable | active | conversation-untitled-rendered |
| chatAppConnectStarted | Chat App Connect Started | channel | active | chat-apps-funnel |
| chatAppConnected | Chat App Connected | channel | active | chat-apps-funnel |
| chatAppDisconnected | Chat App Disconnected | channel | active | chat-apps-funnel |
| chatAppWaitlistJoined | Chat App Waitlist Joined | none | active | chat-apps-funnel |
| paywallOpened | Paywall Opened | source, current_plan | active | subscription-funnel |
| upgradePlanSelected | Upgrade Plan Selected | plan, billing_interval, source | active | subscription-funnel |
| upgradeSucceededAttributed | Upgrade Succeeded Attributed | plan, billing_interval | active | subscription-funnel |
| subscriptionPlanChanged | Subscription Plan Changed | previous_plan, new_plan, billing_interval, change_source | active | subscription-funnel |
| subscriptionCancelReasonSelected | Subscription Cancel Reason Selected | reason | active | subscription-funnel |
| subscriptionCancelConfirmed | Subscription Cancel Confirmed | reason, has_details | active | subscription-funnel |
| subscriptionCancelKeptPlan | Subscription Cancel Kept Plan | step, reason | active | subscription-funnel |
| subscriptionCancelAbandoned | Subscription Cancel Abandoned | step, reason | active | subscription-funnel |
| guidedIntroPayoffShown | Guided Intro Payoff Shown | memories_count, answer_source, latency_ms | active | guided-intro-payoff-presence |
| guidedIntroPayoffContinued | Guided Intro Payoff Continued | none | active | guided-intro-payoff-presence |
| onboardingFirstCaptureShown | Onboarding First Capture Shown | none | active | mobile-instrumentation-presence |
| onboardingFirstCaptureChoiceSelected | Onboarding First Capture Choice Selected | choice | active | mobile-instrumentation-presence |
| onboardingFirstCaptureRecordingStarted | Onboarding First Capture Recording Started | none | active | mobile-instrumentation-presence |
| onboardingFirstCaptureRecordingCompleted | Onboarding First Capture Recording Completed | duration_s, transcript_observed | active | mobile-instrumentation-presence |
| onboardingFirstCaptureConversationShown | Onboarding First Capture Conversation Shown | latency_ms | active | mobile-instrumentation-presence |
| onboardingFirstCaptureEmptyResult | Onboarding First Capture Empty Result | none | active | mobile-instrumentation-presence |
| onboardingFirstCaptureSkipped | Onboarding First Capture Skipped | none | active | mobile-instrumentation-presence |
| onboardingStepCompleted | Onboarding Step Completed | step, index, elapsed_ms, skipped, platform, exit_reason | active | mobile-instrumentation-presence |
| paywallVariantShown | Paywall Variant Shown | variant, source | active | mobile-instrumentation-presence |
| paywallVariantFallback | Paywall Variant Fallback | variant, reason | active | mobile-instrumentation-presence |
| onboardingWebviewShown | Onboarding Webview Shown | none | active | mobile-instrumentation-presence |
| onboardingWebviewCompleted | Onboarding Webview Completed | none | active | mobile-instrumentation-presence |
| onboardingWebviewFallback | Onboarding Webview Fallback | reason | active | mobile-instrumentation-presence |
| captureRecoveryObserved | Capture Recovery Observed | kind, trigger | active | capture-recovery |
| nativeCustodyObserved | Native Custody Observed | outcome | active | native-custody-health |

## App Review Opportunity decisions

`eligible`, `not_ios_or_android`, `storage_error`, `not_familiar`, `migration_cooldown`, `cooldown`, `budget_exhausted`, `version_already_attempted`, `session_already_attempted`, `lifecycle_not_appropriate`, `lifecycle_changed`, `availability_error`, `unavailable`, `request_error`, `recent_bad_experience`

## Backend billing payload fields

`backend_properties` documents the closed Stripe webhook delivery/catalog inventory; these fields are not portable Dart constructor arguments. `$insert_id` is a UUID, `billing_event_id` and `price_id` are bounded to 128 characters, `currency` to 16, `occurred_at` is a nullable ISO 8601 timestamp, and `billing_source` is `stripe_webhook_authoritative_owner`. Portable properties retain the boolean/integer/closed-enum rules.

## Integer sentinel conventions

- `deviceDisconnectedDetailed.reason_code` = `-1`: the disconnect reason is unknown (native sentinel absent).
- `diagnosticsSendFailed.status_code` = `0`: the failure was not an HTTP failure; otherwise the real HTTP status.
