import Foundation

/// Compile-checked `UserDefaults` keys (S-13, BL-004 partial).
///
/// The defect: `UserDefaults` keys were raw inline string literals scattered
/// across the app — `"auth_userId"` alone appeared inline ~18 times. A single
/// typo (`"auth_userld"`) silently reads `nil` with no error, so auth /
/// onboarding state fails to restore and the failure is invisible.
///
/// Routing keys through this enum turns a typo from a silent `nil` into a
/// compile error, and gives the app one source of truth for each key's string.
///
/// This is the auth slice of the migration. New keys should be added here and
/// read/written through the typed `UserDefaults` accessors below rather than as
/// inline literals. The SwiftLint `omi_inline_userdefaults_key` custom rule
/// (in `Desktop/.swiftlint.yml`) is a CI gate that prevents new raw inline
/// `forKey:` string literals from being introduced elsewhere (the baseline
/// may only shrink).
enum DefaultsKey: String {
  case authIsSignedIn = "auth_isSignedIn"
  case authUserEmail = "auth_userEmail"
  case authUserId = "auth_userId"
  case authGivenName = "auth_givenName"
  case authFamilyName = "auth_familyName"
  case authIdToken = "auth_idToken"
  case authRefreshToken = "auth_refreshToken"
  case authTokenExpiry = "auth_tokenExpiry"
  case authTokenUserId = "auth_tokenUserId"  // User ID that owns the stored token
  case authIsImpersonating = "auth_isImpersonating"
  /// Durable local cleanup journal written only after the backend accepts an
  /// account deletion. It survives a crash between HTTP acceptance and the
  /// owner transition, and is cleared only after local teardown completes.
  case acceptedAccountDeletionOwnerId = "accepted_account_deletion_owner_id"
  /// Non-prod gauntlet owner swap: synthetic kernel owner that must NOT replace
  /// `auth_userId` (that mismatch triggers AuthService.clearTokens()).
  case automationOwnerOverride = "automation_owner_override"
  /// Legacy/heal backup of the real Firebase uid when an older swap overwrote
  /// `auth_userId` with a synthetic owner.
  case automationOwnerABackup = "automation_swap_owner_a_backup"
  case chatBridgeMode = "chatBridgeMode"
  case preferredMicrophoneDeviceUID = "preferredMicrophoneDeviceUID"
  case multiChatEnabled = "multiChatEnabled"
  /// Opt-in: proactive notifications are also spoken out loud on delivery.
  case speakNotificationsAloud = "speakNotificationsAloud"
  /// Opt-out (defaults to on): the post-meeting summary share notification —
  /// the persistent notch card offering "Copy link" / "Send to <participant>".
  case meetingSummaryNotificationsEnabled = "meetingSummaryNotificationsEnabled"
  /// Opt-out: when you open an app Omi integrates with but have not connected,
  /// Omi offers the connection once. Defaults to on; the per-integration
  /// budgets in `IntegrationNudgePolicy` are what keep that from being noise.
  case integrationNudgesEnabled = "integrationNudgesEnabled"
  case aiChatWorkingDirectory = "aiChatWorkingDirectory"
  /// JSON array of skill names the user disabled in Settings. Absent or empty
  /// means every skill is enabled. Read by the skill-catalog projection and
  /// exported to the agent runtime as `OMI_DISABLED_SKILLS`, so the toggle
  /// hides a skill from the catalog and from load_skill/search_skills alike.
  case disabledSkillsJSON = "disabledSkillsJSON"
  /// Presence-only marker: the user turned Launch at Login OFF in Settings on
  /// a build that has this key. Absent means "no recorded decline" — the
  /// default-on migration (`OmiApp.migrateLaunchAtLoginDefault`) enables once;
  /// a decline made before this key existed is indistinguishable from a fresh
  /// install and is re-enabled by that one shot. Present means the user's
  /// choice wins and no migration ever re-enables it. Re-enabling from Settings
  /// removes the marker. Never written `false`.
  case launchAtLoginUserDeclined = "launchAtLoginUserDeclined"
  case hasCompletedOnboarding = "hasCompletedOnboarding"
  /// Three-state marker for the one-time first-real-app tap-to-ask card
  /// (`FirstRealAppCardState`): absent = this build has never looked at this
  /// install, `pending` = a fresh install still owes the card, `consumed` = it
  /// fired, or the install gate retired it for a user who was already onboarded
  /// when this build arrived. A `Bool` cannot express the first state, and
  /// conflating "never written" with `false` is the exact ambiguity that made
  /// the launch-at-login V1 migration re-enable a setting the user turned off.
  case firstRealAppCardState = "firstRealAppCardState"
  case onboardingStep = "onboardingStep"
  case onboardingFurthestStep = "onboardingFurthestStep"
  case onboardingMemoryImportOwnerUserId = "onboardingMemoryImportOwnerUserID"
  case onboardingHowDidYouHearSource = "onboardingHowDidYouHearSource"
  case onboardingRole = "onboardingRole"
  case onboardingJustCompleted = "onboardingJustCompleted"
  /// Legacy onboarding ACP session id (pre-kernel `surface_conversations`).
  case onboardingACPSessionId = "onboardingACPSessionId"
  /// Legacy locally persisted onboarding chat messages; kernel journal owns this now.
  case onboardingChatMessages = "onboardingChatMessages"
  /// Mid-onboarding restart marker kept by `OnboardingChatPersistence`.
  case onboardingMidOnboarding = "onboardingMidOnboarding"
  /// Retired-wizard exploration text; only cleared from disk, never written now.
  case onboardingExplorationText = "onboardingExplorationText"
  /// Retired-wizard exploration completion; only cleared from disk, never written now.
  case onboardingExplorationCompleted = "onboardingExplorationCompleted"
  /// `complete_onboarding` tool-call marker kept by `OnboardingChatPersistence`.
  case onboardingToolCompleted = "onboardingToolCompleted"
  /// Monthly-goal answered marker kept by `OnboardingChatPersistence`.
  case onboardingGoalCompleted = "onboardingGoalCompleted"
  case hasCompletedFileIndexing = "hasCompletedFileIndexing"
  /// Durable record that the user skipped Accessibility during onboarding. Absent
  /// means "no recorded skip" (pre-marker onboarding or an Allow); macOS exposes no
  /// denied/notDetermined distinction for AX, so this is the only signal that keeps
  /// the sidebar from pulsing a deliberate skip as "denied".
  case onboardingAccessibilitySkipped = "onboardingAccessibilitySkipped"
  case screenAnalysisEnabled = "screenAnalysisEnabled"
  case ratingPromptQuestionCount = "ratingPromptQuestionCount"
  case ratingPromptSubmittedRating = "ratingPromptSubmittedRating"
  case ratingPromptDismissed = "ratingPromptDismissed"
  /// One-shot marker: the question counter was seeded from server chat
  /// history so long-time users see the rating ask without three NEW questions.
  case ratingPromptHistorySeeded = "ratingPromptHistorySeeded"
  /// Last-good server CSAT config (JSON), so a cold start renders the right
  /// copy before the first config poll lands. Product-wide, not owner-scoped.
  case csatConfigLastGood = "csatConfigLastGood"
  case screenAnalysisAutoStartFixedV2 = "screenAnalysisAutoStartFixed_v2"
  case screenAnalysisAutoStartFixedV3 = "screenAnalysisAutoStartFixed_v3"
  case homeOmiDeviceAccountHistory = "home-omi-device-account-history"
  case pairedDeviceId = "pairedDeviceId"
  case pairedDeviceName = "pairedDeviceName"
  case pairedDeviceType = "pairedDeviceType"
  case chatScreenshotSharingEnabled = "chatScreenshotSharingEnabled"
  /// Client-side mirror of the server's `meeting_note_screenshots_enabled` account setting
  /// (contract §3/§9). Absent key means enabled (default on) — see
  /// `MeetingNoteScreenshotsFeature.isEnabled`.
  case meetingNoteScreenshotsEnabled = "meetingNoteScreenshotsEnabled"
  /// Test hook: forces TTS playback start to report failure (non-prod gauntlets).
  case forceTTSPlaybackStartFalse = "forceTTSPlaybackStartFalse"
  case shortcutPTTInputDeviceUID = "shortcut_pttInputDeviceUID"
  /// One-shot marker: the PTT-only microphone choice has been folded into the shared
  /// `preferredMicrophoneDeviceUID`, so it is never carried over twice.
  case shortcutPTTMicrophoneMergedIntoPreferred = "shortcut_pttMicrophoneMergedIntoPreferred"
  case floatingBarNotificationPreviewsEnabled = "shortcut_floatingBarNotificationPreviewsEnabled"
  case floatingBarCachedPlan = "floatingBar_cachedPlan"
  case floatingBarCachedDesktopGrandfatherUntil = "floatingBar_cachedDesktopGrandfatherUntil"
  case desktopIsPaywalled = "desktop_isPaywalled"
  case askOmiBarEnabled = "askOmiBarEnabled"
  case byokLLMProvider = "dev_byok_llm_provider"
  /// Provider → SHA-256 fingerprint last enrolled after BYOKValidator .ok.
  case byokEnrolledFingerprints = "byok_enrolled_fingerprints"
  /// UID that last owned persisted BYOK keys on this Mac.
  case byokOwnerUid = "byok_owner_uid"
  case rewindDisableContentCache = "rewindDisableContentCache"
  // Task-order migration keys are typed so TasksPage and its tests share the
  // migration contract instead of repeating raw UserDefaults literals.
  case tasksCategoryOrder = "TasksCategoryOrder"
  case tasksSortOrderMigrated = "TasksSortOrderMigrated"
  /// Whether the Suggested candidate section on the Tasks page is expanded.
  /// Shared by the view (@AppStorage) and deep-link expand-before-scroll.
  case tasksSuggestionsSectionExpanded = "tasksSuggestionsSectionExpanded"
  case onboardingChatGPTImportedMemories = "onboardingChatGPTImportedMemoriesCount"
  case gmailSelectedCookiePath = "gmailSelectedCookiePath"
  case gmailSelectedAccountLabel = "gmailSelectedAccountLabel"
  /// Preferred summarization app for conversation summaries; locally mirrored
  /// (the backend exposes no GET) and pushed via
  /// `PUT /v1/users/preferences/app`. Same name mobile uses in SharedPreferences.
  case preferredSummarizationAppId = "preferredSummarizationAppId"
  case disableSystemAudioCapture = "disableSystemAudioCapture"
}

/// Compile-checked owner-scoped defaults keys whose final storage key is
/// derived at runtime.
struct ScopedDefaultsKey {
  fileprivate let rawValue: String

  static func taskContextSubjectMatches(ownerHash: String) -> Self {
    Self(rawValue: "taskContextSubjectMatches.v1.\(ownerHash)")
  }

  static func trialNudge(_ kind: String, ownerHash: String) -> Self {
    Self(rawValue: "trial_nudge.v1.\(kind).\(ownerHash)")
  }

  /// Dismissed chat-quota warnings. Entries carry their own billing cycle, so
  /// the set expires on its own instead of needing a sweep.
  static func chatQuotaBannerDismissals(ownerHash: String) -> Self {
    Self(rawValue: "chat_quota_banner_dismissals.v1.\(ownerHash)")
  }

  static func tasksFullSyncCompleted(ownerID: String) -> Self {
    Self(rawValue: "tasksFullSyncCompleted_v9_\(ownerID)")
  }

  static func restoreLegacyConversationItemsCompleted(ownerID: String) -> Self {
    Self(rawValue: "restoreLegacyConversationItemsCompleted_v1_\(ownerID)")
  }

  /// Owner-scoped key for the legacy task-order migration completion marker.
  static func tasksSortOrderMigrated(ownerID: String) -> Self {
    Self(rawValue: "TasksSortOrderMigrated.owner.\(ownerID)")
  }

  static func pendingCanonicalReceiptInvalidation(
    ownerID: String,
    keyPrefix: String = "suggested.canonicalReceipt.pendingInvalidation."
  ) -> Self {
    Self(rawValue: "\(keyPrefix)\(ownerID)")
  }

  static func pendingCanonicalReceiptInvalidationTimestamps(
    ownerID: String,
    keyPrefix: String = "suggested.canonicalReceipt.pendingInvalidation."
  ) -> Self {
    Self(rawValue: "\(keyPrefix)\(ownerID).timestamps")
  }

  /// Owner-scoped proactive integration-nudge history. `field` is one of the
  /// closed set the store writes (`shownCount`, `lastShownAt`, `snoozedUntil`,
  /// `optedOut`); `scope` is the catalog telemetry id plus the owner id, so one
  /// person's dismissals never silence an integration for another account on
  /// the same Mac.
  static func integrationNudge(_ field: String, scope: String) -> Self {
    Self(rawValue: "integrationNudge.v1.\(field).\(scope)")
  }

  /// Owner-scoped cross-integration nudge budget (last delivery, and the
  /// delivery timestamps inside the trailing day window).
  static func integrationNudgeBudget(_ field: String, ownerID: String) -> Self {
    Self(rawValue: "integrationNudgeBudget.v1.\(field).\(ownerID)")
  }

  /// Owner-scoped id of the newest daily summary the owner has already been shown a notch card
  /// for. Desktop receives no `daily_summary` push, so this is what keeps the announcement at
  /// most once per summary, and per account on a shared Mac.
  static func dailySummaryLastSeenID(ownerID: String) -> Self {
    Self(rawValue: "dailySummary.lastSeenID.v1.\(ownerID)")
  }

  /// Owner-scoped id of the daily summary that was on screen when the owner last cleared Chat.
  /// The card is chrome rather than a turn (INV-CHAT-1), so clearing the transcript cannot
  /// delete it — this is what makes Clear take it away anyway, until a newer summary arrives.
  static func dailySummaryClearedID(ownerID: String) -> Self {
    Self(rawValue: "dailySummary.clearedID.v1.\(ownerID)")
  }

  static func importConnectorAvailabilityText(connectorID: String) -> Self {
    Self(rawValue: "appsImportConnectorAvailabilityText.\(connectorID)")
  }

  static func importConnectorSourceCount(connectorID: String) -> Self {
    Self(rawValue: "appsImportConnectorSourceCount.\(connectorID)")
  }

  /// Per-prompt, per-account resolution of a remote (admin-authored) prompt:
  /// "answered" or "dismissed". Absent = still eligible. Owner-scoped so one
  /// account's answer never suppresses prompts for another account on the
  /// same Mac (the #9821 account-switch-bleed class).
  static func remotePromptResolution(promptId: String, ownerID: String) -> Self {
    Self(rawValue: "remotePrompt.resolution.v2.\(ownerID).\(promptId)")
  }

  /// Owner-scoped rating-prompt state (count / submitted / dismissed /
  /// historySeeded) — same bleed class as above.
  static func ratingPrompt(_ field: String, ownerID: String) -> Self {
    Self(rawValue: "ratingPrompt.v2.\(field).\(ownerID)")
  }

  static func taskInterruptionLedger(ownerID: String) -> Self {
    Self(rawValue: "proactiveTaskInterruptionLedger.v1.\(ownerID)")
  }

  static func suggestionTaskNudgeLedger(ownerID: String) -> Self {
    Self(rawValue: "suggestionTaskNudgeLedger.v1.\(ownerID)")
  }

}

/// Typed accessors that take a `DefaultsKey` instead of a `String`.
///
/// Each forwards to the stdlib `String`-keyed method via `key.rawValue`, so
/// overload resolution picks the stdlib method (no recursion). Call sites read
/// as `UserDefaults.standard.string(forKey: .authUserId)` — the key is now
/// compiler-checked.
extension UserDefaults {
  func string(forKey key: DefaultsKey) -> String? { string(forKey: key.rawValue) }
  func bool(forKey key: DefaultsKey) -> Bool { bool(forKey: key.rawValue) }
  func integer(forKey key: DefaultsKey) -> Int { integer(forKey: key.rawValue) }
  func double(forKey key: DefaultsKey) -> Double { double(forKey: key.rawValue) }
  func string(forKey key: ScopedDefaultsKey) -> String? { string(forKey: key.rawValue) }
  func data(forKey key: ScopedDefaultsKey) -> Data? { data(forKey: key.rawValue) }
  func bool(forKey key: ScopedDefaultsKey) -> Bool { bool(forKey: key.rawValue) }
  func integer(forKey key: ScopedDefaultsKey) -> Int { integer(forKey: key.rawValue) }
  func double(forKey key: ScopedDefaultsKey) -> Double { double(forKey: key.rawValue) }
  func array(forKey key: ScopedDefaultsKey) -> [Any]? { array(forKey: key.rawValue) }
  func stringArray(forKey key: ScopedDefaultsKey) -> [String]? { stringArray(forKey: key.rawValue) }
  func dictionary(forKey key: ScopedDefaultsKey) -> [String: Any]? {
    dictionary(forKey: key.rawValue)
  }
  func object(forKey key: ScopedDefaultsKey) -> Any? { object(forKey: key.rawValue) }
  func object(forKey key: DefaultsKey) -> Any? { object(forKey: key.rawValue) }

  func set(_ value: Any?, forKey key: DefaultsKey) { set(value, forKey: key.rawValue) }
  func set(_ value: Any?, forKey key: ScopedDefaultsKey) { set(value, forKey: key.rawValue) }
  func removeObject(forKey key: DefaultsKey) { removeObject(forKey: key.rawValue) }
  func removeObject(forKey key: ScopedDefaultsKey) { removeObject(forKey: key.rawValue) }
}
