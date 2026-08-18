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
  case aiChatWorkingDirectory = "aiChatWorkingDirectory"
  case hasCompletedOnboarding = "hasCompletedOnboarding"
  case onboardingStep = "onboardingStep"
  case onboardingFurthestStep = "onboardingFurthestStep"
  case onboardingMemoryImportOwnerUserId = "onboardingMemoryImportOwnerUserID"
  case onboardingHowDidYouHearSource = "onboardingHowDidYouHearSource"
  case onboardingRole = "onboardingRole"
  case onboardingJustCompleted = "onboardingJustCompleted"
  case hasCompletedFileIndexing = "hasCompletedFileIndexing"
  case screenAnalysisEnabled = "screenAnalysisEnabled"
  case screenAnalysisAutoStartFixedV2 = "screenAnalysisAutoStartFixed_v2"
  case screenAnalysisAutoStartFixedV3 = "screenAnalysisAutoStartFixed_v3"
  case homeOmiDeviceAccountHistory = "home-omi-device-account-history"
  case pairedDeviceId = "pairedDeviceId"
  case pairedDeviceName = "pairedDeviceName"
  case pairedDeviceType = "pairedDeviceType"
  case chatScreenshotSharingEnabled = "chatScreenshotSharingEnabled"
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

  static func importConnectorAvailabilityText(connectorID: String) -> Self {
    Self(rawValue: "appsImportConnectorAvailabilityText.\(connectorID)")
  }

  static func importConnectorSourceCount(connectorID: String) -> Self {
    Self(rawValue: "appsImportConnectorSourceCount.\(connectorID)")
  }

  static func taskInterruptionLedger(ownerID: String) -> Self {
    Self(rawValue: "proactiveTaskInterruptionLedger.v1.\(ownerID)")
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
  func data(forKey key: ScopedDefaultsKey) -> Data? { data(forKey: key.rawValue) }
  func bool(forKey key: ScopedDefaultsKey) -> Bool { bool(forKey: key.rawValue) }
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
